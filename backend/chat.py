"""POST /api/chat - stylist chat turn (orchestrator -> category agents).

Two paths:

* **Demo path** - when ``DEMO_MODE=1`` OR ``AGENTCORE_AGENT_ARN`` is unset, we
  return a polished, weather-aware canned stylist reply so the site works end to
  end before the agents deploy. The reply is composed from the posted session
  context (city + 3-day forecast) and reads like the orchestrator (nova-pro)
  handed off to the category agents (haiku-4.5).

* **Live path** - when ``DEMO_MODE=0`` and the ARN is set, we invoke the
  AgentCore Runtime orchestrator via the ``bedrock-agentcore`` data plane
  ``InvokeAgentRuntime`` and relay its reply. Model ids are never named here -
  all model access flows through the AgentCore runtime + LiteLLM gateway.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Mapping

import boto3

_LOG = logging.getLogger(__name__)

# AgentCore InvokeAgentRuntime requires runtimeSessionId to be >= 33 chars.
# A Cognito ``sub`` (a 36-char UUID) satisfies this, but demo/anonymous ids do
# not, so we always normalize to a stable, compliant session id.
_MIN_SESSION_ID_LEN = 33

from common.http import (
    error,
    get_method,
    get_user_id,
    parse_body,
    preflight,
    respond,
)

# The eight-agent roster (name -> workload identity), kept in one place so the
# canned reply can credit agents with their real wid identities.
_ROSTER = {
    "orchestrator": "adidlabs/orchestrator-9f21",
    "weather": "adidlabs/weather-3b7c",
    "shoes": "adidlabs/shoes-4e2a",
    "pants": "adidlabs/pants-8c1d",
    "tshirt": "adidlabs/tshirt-2a9e",
    "jumper": "adidlabs/jumper-6d3f",
    "jacket": "adidlabs/jacket-1e8b",
    "accessory": "adidlabs/accessory-5c4a",
}


# WMO weather codes (Open-Meteo daily) -> coarse buckets + short labels, so
# forecast day rows that carry ``weathercode`` instead of a ``label`` still
# drive wet/cold detection and read naturally in the context line.
_WET_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}
_CODE_LABELS = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 80: "showers", 81: "showers",
    82: "heavy showers", 95: "thunderstorms", 96: "thunderstorms",
    99: "thunderstorms",
}


def _demo_mode() -> bool:
    """True when DEMO_MODE is set truthy or no AgentCore ARN is configured."""
    flag = os.environ.get("DEMO_MODE", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    return not os.environ.get("AGENTCORE_AGENT_ARN")


def _extract_session(body: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the chat body into one session dict: city/region + weather days.

    The SPA posts ``{message, context: {session, weather}}`` (StylistChat), while
    tests and older clients post a top-level ``session``. Accept both, and fold
    a separate ``weather`` payload into ``session["weather"]["days"]`` so every
    downstream helper has a single place to look.
    """
    ctx = body.get("context") or {}
    if not isinstance(ctx, Mapping):
        ctx = {}
    session = dict(body.get("session") or ctx.get("session") or {})
    weather = ctx.get("weather") or body.get("weather") or session.get("weather") or {}
    if isinstance(weather, list):
        days = weather
    elif isinstance(weather, Mapping):
        days = weather.get("days") or []
    else:
        days = []
    if days:
        session["weather"] = {"days": days}
    return session


def _session_days(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    weather = session.get("weather") or {}
    days = weather.get("days") if isinstance(weather, Mapping) else None
    return list(days or session.get("days") or [])


def _day_label(day: Mapping[str, Any]) -> str:
    label = str(day.get("label") or "").strip().lower()
    if label:
        return label
    code = day.get("weathercode")
    if isinstance(code, (int, float)):
        return _CODE_LABELS.get(int(code), "")
    return ""


def _context_line(session: Mapping[str, Any]) -> str:
    """One grounding line prefixed to live replies so the chat always reports
    the place and forecast, e.g. ``Milan, IT — next 3 days: TUE 31°/23°
    showers · WED 29°/20° partly cloudy · THU 31°/20° overcast``."""
    city = session.get("city")
    region = session.get("region") or session.get("country")
    place = f"{city}, {region}" if city and region else (city or "")
    parts: list[str] = []
    for d in _session_days(session)[:3]:
        seg = str(d.get("day") or d.get("date") or "").strip()
        hi, lo = d.get("hi"), d.get("lo")
        if isinstance(hi, (int, float)) and isinstance(lo, (int, float)):
            seg = f"{seg} {round(hi)}°/{round(lo)}°".strip()
        label = _day_label(d)
        if label:
            seg = f"{seg} {label}".strip()
        if seg:
            parts.append(seg)
    if not parts:
        return place
    line = " · ".join(parts)
    return f"{place} — next 3 days: {line}" if place else f"Next 3 days: {line}"


def _forecast_summary(session: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Derive a human forecast phrase + normalized day list from session ctx.

    Accepts the ``session`` object the SPA posts, which may embed a ``weather``
    payload (``{days: [...]}``) plus ``city``/``region``. Returns a short phrase
    and the (possibly empty) day list.
    """
    weather = session.get("weather") or {}
    days = weather.get("days") if isinstance(weather, dict) else None
    days = days or session.get("days") or []
    if not days:
        return ("your local 3-day forecast", [])
    hi = [d.get("hi") for d in days if isinstance(d.get("hi"), (int, float))]
    lo = [d.get("lo") for d in days if isinstance(d.get("lo"), (int, float))]
    labels = {_day_label(d) for d in days}
    codes = {int(d["weathercode"]) for d in days
             if isinstance(d.get("weathercode"), (int, float))}
    wet = any(w in " ".join(labels) for w in ("rain", "drizzle", "shower", "thunder")) \
        or bool(codes & _WET_CODES)
    cold = (bool(lo) and min(lo) <= 8) or bool(codes & _SNOW_CODES)
    warm = bool(hi) and max(hi) >= 24
    band = "mild"
    if cold and not warm:
        band = "cold"
    elif warm and not cold:
        band = "warm"
    elif warm and cold:
        band = "swinging"
    phrase = f"a {band} 3-day stretch"
    if wet:
        phrase += " with some wet spells"
    return (phrase, days)


def _canned_reply(message: str, session: dict[str, Any]) -> dict[str, Any]:
    """Compose a convincing, weather-matched stylist reply (no model call).

    Reads like the nova-pro orchestrator fanned out to the haiku-4.5 category
    agents. Picks are fictional AdidLaBs items with synthetic EUR prices.
    """
    city = session.get("city") or "your city"
    region = session.get("region")
    place = f"{city}, {region}" if region else city
    phrase, days = _forecast_summary(session)

    wet = "wet" in phrase
    cold = "cold" in phrase
    warm = "warm" in phrase

    # Category agents each contribute one pick, tuned to the forecast band.
    outer = (
        {"category": "JACKET", "title": "Stormline Shell Jacket", "price": 149.00}
        if (wet or cold)
        else {"category": "JUMPER", "title": "Featherweight Knit Jumper", "price": 79.00}
    )
    top = {"category": "TSHIRT", "title": "Aircell Performance Tee", "price": 39.00}
    bottom = (
        {"category": "PANTS", "title": "Thermo Track Trouser", "price": 89.00}
        if cold
        else {"category": "PANTS", "title": "Breeze Woven Jogger", "price": 69.00}
    )
    footwear = (
        {"category": "SHOES", "title": "Gripline Trail Runner", "price": 129.00}
        if wet
        else {"category": "SHOES", "title": "Cloudstep Everyday Runner", "price": 119.00}
    )
    accessory = (
        {"category": "ACCESSORY", "title": "Packable Rain Cap", "price": 29.00}
        if wet
        else {"category": "ACCESSORY", "title": "Everyday Crossbody Pouch", "price": 34.00}
    )

    picks = [footwear, bottom, top, outer, accessory]
    for i, p in enumerate(picks):
        p["item_id"] = f"demo-{p['category'].lower()}-{i+1}"
        p["deal"] = i == 0  # feature the shoe as a deal for the red-price look
        if p["deal"]:
            p["original_price"] = round(p["price"] * 1.25, 2)
            p["discount_pct"] = 20

    warmth_note = (
        "Layer up - mornings bite, so the shell earns its place."
        if cold
        else ("Keep it breathable; the tee handles the warm hours." if warm else "")
    )
    rain_note = "Grab the trail runner and rain cap for the wet windows." if wet else ""

    reply_lines = [
        f"Reading {place} - I'm seeing {phrase}.",
        "Here's a weather-matched look my category agents pulled together:",
    ]
    for p in picks:
        price_txt = f"€{p['price']:.0f}"
        if p.get("deal"):
            price_txt = f"~~€{p['original_price']:.0f}~~ €{p['price']:.0f} (-{p['discount_pct']}%)"
        reply_lines.append(f"- {p['category'].title()}: {p['title']} - {price_txt}")
    tail = " ".join(t for t in (warmth_note, rain_note) if t)
    if tail:
        reply_lines.append(tail)
    reply_lines.append("Say the word and I'll drop any of these in your bag.")

    return {
        "mode": "demo",
        "reply": "\n".join(reply_lines),
        "picks": picks,
        "forecastDays": days,
        "agents": [
            {"name": "ORCHESTRATOR", "wid": _ROSTER["orchestrator"], "route": "nova-pro"},
            {"name": "WEATHER", "wid": _ROSTER["weather"], "route": "haiku-4.5"},
            {"name": "SHOES", "wid": _ROSTER["shoes"], "route": "haiku-4.5"},
            {"name": "PANTS", "wid": _ROSTER["pants"], "route": "haiku-4.5"},
            {"name": "TSHIRT", "wid": _ROSTER["tshirt"], "route": "haiku-4.5"},
            {"name": "JUMPER", "wid": _ROSTER["jumper"], "route": "haiku-4.5"},
            {"name": "JACKET", "wid": _ROSTER["jacket"], "route": "haiku-4.5"},
            {"name": "ACCESSORY", "wid": _ROSTER["accessory"], "route": "haiku-4.5"},
        ],
    }


def _session_id(user_id: str) -> str:
    """Return a runtimeSessionId that satisfies the >= 33-char AgentCore rule.

    Stable per user (same user -> same session id) so multi-turn context sticks.
    Short ids (demo/anonymous) are deterministically expanded with a hash suffix;
    already-long ids (a Cognito UUID ``sub``) pass through unchanged.
    """
    if len(user_id) >= _MIN_SESSION_ID_LEN:
        return user_id
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"{user_id}-{digest}"[:64]


def _invoke_runtime(user_id: str, message: str, session: dict[str, Any]) -> dict[str, Any]:
    """Invoke the AgentCore Runtime orchestrator and relay its reply.

    Uses the ``bedrock-agentcore`` data-plane ``InvokeAgentRuntime`` API with the
    configured ``AGENTCORE_AGENT_ARN``. The payload carries the user message and
    session context (location + forecast) so the orchestrator can ground on it.
    """
    arn = os.environ["AGENTCORE_AGENT_ARN"]
    client = boto3.client(
        "bedrock-agentcore",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
    )
    # The runtime entrypoint contract wants ``forecast`` in Open-Meteo daily
    # shape (agents/entrypoint.py); convert the SPA's day rows into it so the
    # orchestrator grounds its picks on the real 3-day window instead of the
    # mild default.
    days = _session_days(session)
    forecast: dict[str, Any] = {}
    if days:
        forecast = {
            "daily": {
                "time": [str(d.get("date") or d.get("day") or "") for d in days],
                "weathercode": [
                    int(d["weathercode"])
                    if isinstance(d.get("weathercode"), (int, float)) else 3
                    for d in days
                ],
                "temperature_2m_max": [d.get("hi") for d in days],
                "temperature_2m_min": [d.get("lo") for d in days],
            }
        }
    payload = json.dumps(
        {"user_id": user_id, "message": message, "forecast": forecast,
         "session": session}
    ).encode("utf-8")

    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=_session_id(user_id),
        payload=payload,
        contentType="application/json",
        accept="application/json",
    )

    # The response body is a streaming/bytes payload; normalize to text/JSON.
    raw = resp.get("response")
    if hasattr(raw, "read"):
        raw = raw.read()
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")

    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {"reply": raw or ""}

    data.setdefault("mode", "live")

    # Always report the place + forecast the turn was grounded on: the
    # orchestrator reply covers picks, this line covers the context.
    context_line = _context_line(session)
    reply = data.get("reply")
    if context_line and isinstance(reply, str) and reply:
        data["reply"] = f"{context_line}\n\n{reply}"
    return data


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for POST /api/chat."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "POST":
        return error(405, "method not allowed")

    user_id = get_user_id(event)

    try:
        body = parse_body(event)
    except ValueError as exc:
        return error(400, f"invalid JSON body: {exc}")

    message = (body.get("message") or "").strip()
    session = _extract_session(body)
    if not message:
        return error(400, "message is required")

    if _demo_mode():
        return respond(200, _canned_reply(message, session))

    try:
        return respond(200, _invoke_runtime(user_id, message, session))
    except Exception:  # noqa: BLE001 - never leave the drawer hanging
        # Degrade gracefully to the canned reply so the demo keeps working even
        # if the runtime is mid-deploy; flag it so the caller can tell. The real
        # cause is logged server-side; the client only sees a generic marker so
        # upstream/runtime internals never leak to the browser.
        _LOG.exception("AgentCore InvokeAgentRuntime failed for user_id=%s", user_id)
        fallback = _canned_reply(message, session)
        fallback["mode"] = "demo-fallback"
        fallback["runtimeError"] = "runtime unavailable"
        return respond(200, fallback)

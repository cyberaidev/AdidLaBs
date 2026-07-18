"""GET /api/weather - 3-day forecast via Open-Meteo (keyless).

Open-Meteo requires no API key. We request daily min/max temperature and a
weathercode for three days at a given lat/lon, then map each weathercode to an
emoji the black weather bar renders (design Sec. 5.6).

Coordinates come from query params ``lat`` / ``lon`` (the frontend passes the
values it got from ``/api/session``). If they are missing we fall back to
Sydney so the demo bar always renders.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Mapping

from common.geo import SYDNEY_FALLBACK
from common.http import error, get_method, get_query, preflight, respond

_LOG = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 4.0

# WMO weathercode -> (emoji, short label). Grouped per Open-Meteo docs.
# Documented here so the frontend and backend agree on the glyph set.
_WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("☀️", "Clear"),          # sun
    1: ("\U0001f324️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),       # cloud
    45: ("\U0001f32b️", "Fog"),
    48: ("\U0001f32b️", "Rime fog"),
    51: ("\U0001f326️", "Light drizzle"),
    53: ("\U0001f326️", "Drizzle"),
    55: ("\U0001f327️", "Dense drizzle"),
    56: ("\U0001f327️", "Freezing drizzle"),
    57: ("\U0001f327️", "Freezing drizzle"),
    61: ("\U0001f327️", "Light rain"),   # rain
    63: ("\U0001f327️", "Rain"),
    65: ("\U0001f327️", "Heavy rain"),
    66: ("\U0001f327️", "Freezing rain"),
    67: ("\U0001f327️", "Freezing rain"),
    71: ("❄️", "Light snow"),       # snow
    73: ("❄️", "Snow"),
    75: ("❄️", "Heavy snow"),
    77: ("❄️", "Snow grains"),
    80: ("\U0001f326️", "Rain showers"),
    81: ("\U0001f327️", "Rain showers"),
    82: ("⛈️", "Violent showers"),
    85: ("\U0001f328️", "Snow showers"),
    86: ("\U0001f328️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm + hail"),
    99: ("⛈️", "Thunderstorm + hail"),
}

_DEFAULT_GLYPH = ("⛅", "Unknown")


def _emoji_for(code: int | None) -> tuple[str, str]:
    """Map a WMO weathercode to (emoji, label), defaulting to partly cloudy.

    Open-Meteo can legitimately return a ``null`` weathercode for a day with
    only partial data, so ``code`` may be ``None`` (or a non-numeric string).
    We coerce anything uncoercible to the default glyph instead of raising a
    ``TypeError`` from ``int(None)`` - an uncaught crash there would return a
    raw 500 with no CORS headers and leak a stack trace to the browser.
    """
    if code is None:
        return _DEFAULT_GLYPH
    try:
        return _WEATHER_CODES.get(int(code), _DEFAULT_GLYPH)
    except (TypeError, ValueError):
        return _DEFAULT_GLYPH


def _day_name(iso_date: str) -> str:
    """Return the 3-letter uppercase weekday for an ISO ``YYYY-MM-DD`` date."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%a").upper()
    except (TypeError, ValueError):
        return iso_date


def _fetch_forecast(lat: float, lon: float) -> dict[str, Any]:
    """Call Open-Meteo for a 3-day daily forecast at lat/lon."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weathercode,temperature_2m_max,temperature_2m_min",
        "forecast_days": 3,
        "timezone": "auto",
    }
    url = f"{_OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AdidLaBs/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _shape(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Reshape Open-Meteo's parallel arrays into a list of 3 day objects."""
    daily = raw.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weathercode") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    days: list[dict[str, Any]] = []
    for i in range(min(3, len(dates))):
        raw_code = codes[i] if i < len(codes) else 0
        # ``_emoji_for`` tolerates a null/partial code; normalise the stored
        # weathercode to 0 so the emitted JSON always carries a valid int
        # (the frontend chip contract) even on a partial-data day.
        emoji, label = _emoji_for(raw_code)
        code = raw_code if raw_code is not None else 0
        days.append(
            {
                "date": dates[i],
                "day": _day_name(dates[i]),
                "weathercode": code,
                "emoji": emoji,
                "label": label,
                "hi": round(highs[i]) if i < len(highs) and highs[i] is not None else None,
                "lo": round(lows[i]) if i < len(lows) and lows[i] is not None else None,
            }
        )
    return days


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/weather."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    q = get_query(event)
    try:
        lat = float(q["lat"]) if q.get("lat") not in (None, "") else SYDNEY_FALLBACK["lat"]
        lon = float(q["lon"]) if q.get("lon") not in (None, "") else SYDNEY_FALLBACK["lon"]
    except (TypeError, ValueError):
        return error(400, "lat and lon must be numeric")

    # Both the network fetch AND the reshape run under one guard: a malformed
    # or partial Open-Meteo payload (e.g. a null weathercode entry) must never
    # escape as an uncaught 500 - that response would carry NO CORS headers and
    # leak a stack trace. _emoji_for/_shape are already null-tolerant; this is
    # belt-and-braces so any residual shaping error still degrades to a clean
    # 502 with CORS.
    try:
        raw = _fetch_forecast(lat, lon)
        days = _shape(raw)
    except Exception:  # noqa: BLE001 - upstream/network/shape failure -> 502
        # Log the real cause server-side; never echo upstream/runtime internals
        # to the browser (leak-free client message).
        _LOG.exception("Open-Meteo forecast build failed for lat=%s lon=%s", lat, lon)
        return error(502, "weather upstream unavailable")

    if not days:
        return error(502, "weather upstream returned no forecast")

    return respond(
        200,
        {
            "lat": lat,
            "lon": lon,
            "units": {"temperature": "celsius"},
            "days": days,
        },
    )

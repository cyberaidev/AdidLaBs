"""Weather agent - Open-Meteo 3-day forecast -> structured conditions.

The weather agent (``adidlabs/weather-3b7c``, route ``haiku-4.5``) turns a raw
Open-Meteo 3-day daily forecast into a compact "conditions" object the
orchestrator can reason over: a dominant condition band (``rain``/``sun``/
``cold``/``mild``), temperature range, and precipitation/wind cues. It also
produces a short natural-language read.

Open-Meteo is free and keyless. The agent accepts an already-fetched forecast
payload (the api-handler / session layer fetches it and passes it in), so this
module has no hard network dependency and stays unit-testable. If no forecast is
supplied it can fetch one itself via the stdlib as a convenience.

Weather-code mapping follows the WMO codes Open-Meteo returns.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# Dual-mode imports: package-relative for tests/tooling (agents.entrypoint), and
# top-level for the AgentCore runtime, which runs this file as /var/task/<name>.py
# with no parent package (direct code deploy zips the agents/ dir contents at root).
try:
    from .common.llm import LLMClient
    from .common.roster import get_identity
except ImportError:  # pragma: no cover - runtime layout
    from common.llm import LLMClient
    from common.roster import get_identity

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code -> (label, emoji, coarse condition bucket).
# https://open-meteo.com/en/docs (weathercode table).
_WMO: dict[int, tuple[str, str, str]] = {
    0: ("Clear sky", "☀️", "sun"),
    1: ("Mainly clear", "\U0001f324️", "sun"),
    2: ("Partly cloudy", "⛅", "mild"),
    3: ("Overcast", "☁️", "mild"),
    45: ("Fog", "\U0001f32b️", "mild"),
    48: ("Rime fog", "\U0001f32b️", "mild"),
    51: ("Light drizzle", "\U0001f326️", "rain"),
    53: ("Drizzle", "\U0001f326️", "rain"),
    55: ("Dense drizzle", "\U0001f327️", "rain"),
    61: ("Light rain", "\U0001f327️", "rain"),
    63: ("Rain", "\U0001f327️", "rain"),
    65: ("Heavy rain", "\U0001f327️", "rain"),
    71: ("Light snow", "\U0001f328️", "cold"),
    73: ("Snow", "\U0001f328️", "cold"),
    75: ("Heavy snow", "❄️", "cold"),
    80: ("Rain showers", "\U0001f327️", "rain"),
    81: ("Rain showers", "\U0001f327️", "rain"),
    82: ("Violent showers", "⛈️", "rain"),
    95: ("Thunderstorm", "⛈️", "rain"),
    96: ("Thunderstorm + hail", "⛈️", "rain"),
    99: ("Thunderstorm + hail", "⛈️", "rain"),
}
_DEFAULT_CODE = ("Unknown", "\U0001f321️", "mild")


# Explicit weather intents a shopper can name ("any snow options?"). Maps
# message keywords -> (condition bucket, human label). Checked in order;
# first hit wins. Deliberately simple and deterministic.
_MESSAGE_INTENTS: list[tuple[frozenset, str, str]] = [
    (frozenset({"snow", "snowy", "ski", "skiing", "blizzard", "sleet", "slopes"}), "cold", "snow"),
    (frozenset({"freezing", "winter", "frost", "icy", "ice"}), "cold", "winter cold"),
    (frozenset({"cold", "chilly", "cool"}), "cold", "cold weather"),
    (frozenset({"rain", "rainy", "wet", "storm", "stormy", "shower", "showers",
                "drizzle", "downpour", "monsoon"}), "rain", "rain"),
    (frozenset({"hot", "heat", "heatwave", "sunny", "sun", "summer", "beach", "uv"}), "sun", "heat and sun"),
    (frozenset({"wind", "windy", "breezy", "gale"}), "rain", "wind"),
]


def intent_override(message: str) -> tuple[str, str] | None:
    """Detect an explicit weather ask in a shopper message.

    Returns ``(bucket, label)`` for the first matching intent (e.g. "snow
    options?" -> ``("cold", "snow")``) or ``None`` when the shopper named no
    condition, in which case the live forecast rules the routing.
    """
    tokens = set(re.findall(r"[a-z]+", (message or "").lower()))
    for keywords, bucket, label in _MESSAGE_INTENTS:
        if tokens & keywords:
            return bucket, label
    return None

# Temperature thresholds (deg C) used to override the code bucket toward warmth.
_COLD_MAX_C = 12.0
_WARM_MIN_C = 22.0


@dataclass
class DayForecast:
    """One normalized forecast day."""

    day: str
    code: int
    label: str
    emoji: str
    condition: str
    hi_c: float
    lo_c: float


@dataclass
class Conditions:
    """Structured 3-day conditions the orchestrator reasons over.

    Attributes:
        dominant: The single most relevant condition across the window - one of
            ``"rain"``, ``"sun"``, ``"cold"``, ``"mild"``. Drives routing.
        days: The three normalized :class:`DayForecast` entries.
        hi_c / lo_c: Overall high/low across the window.
        is_wet: True if any day is a rain/precip day.
        summary: Short natural-language read.
    """

    dominant: str
    days: list[DayForecast] = field(default_factory=list)
    hi_c: float = 0.0
    lo_c: float = 0.0
    is_wet: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant": self.dominant,
            "hi_c": self.hi_c,
            "lo_c": self.lo_c,
            "is_wet": self.is_wet,
            "summary": self.summary,
            "days": [
                {
                    "day": d.day,
                    "code": d.code,
                    "label": d.label,
                    "emoji": d.emoji,
                    "condition": d.condition,
                    "hi_c": d.hi_c,
                    "lo_c": d.lo_c,
                }
                for d in self.days
            ],
        }


def classify_code(code: int) -> tuple[str, str, str]:
    """Map a WMO weather code to ``(label, emoji, condition_bucket)``."""
    return _WMO.get(int(code), _DEFAULT_CODE)


def fetch_open_meteo(lat: float, lon: float, *, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch a raw 3-day daily forecast from Open-Meteo (free, no key).

    Returned shape matches Open-Meteo's ``daily`` block. Network use only;
    callers with a pre-fetched payload should pass it to :func:`normalize`.
    """
    query = urllib.parse.urlencode(
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min",
            "forecast_days": 3,
            "timezone": "auto",
        }
    )
    with urllib.request.urlopen(f"{_OPEN_METEO_URL}?{query}", timeout=timeout) as resp:  # pragma: no cover - network
        return json.loads(resp.read().decode("utf-8"))


def normalize(forecast: dict[str, Any]) -> Conditions:
    """Normalize a raw Open-Meteo payload into :class:`Conditions`.

    Accepts either the full Open-Meteo response (with a ``daily`` block) or the
    ``daily`` block directly. Picks the dominant condition by priority
    (rain > cold > sun > mild), with a temperature override: a window whose
    overall high is below :data:`_COLD_MAX_C` skews to ``cold``, and a warm
    clear window skews to ``sun``.
    """
    daily = forecast.get("daily", forecast) if isinstance(forecast, dict) else {}
    times = list(daily.get("time", []))[:3]
    codes = list(daily.get("weathercode", []))[:3]
    highs = list(daily.get("temperature_2m_max", []))[:3]
    lows = list(daily.get("temperature_2m_min", []))[:3]

    days: list[DayForecast] = []
    for i, ts in enumerate(times):
        code = int(codes[i]) if i < len(codes) else 3
        label, emoji, bucket = classify_code(code)
        hi = float(highs[i]) if i < len(highs) else 0.0
        lo = float(lows[i]) if i < len(lows) else 0.0
        days.append(
            DayForecast(
                day=_weekday(ts),
                code=code,
                label=label,
                emoji=emoji,
                condition=bucket,
                hi_c=hi,
                lo_c=lo,
            )
        )

    if not days:
        return Conditions(dominant="mild", summary="No forecast data available.")

    overall_hi = max(d.hi_c for d in days)
    overall_lo = min(d.lo_c for d in days)
    is_wet = any(d.condition == "rain" for d in days)

    dominant = _dominant_condition(days, overall_hi)
    summary = _summarize(days, dominant, overall_hi, overall_lo)
    return Conditions(
        dominant=dominant,
        days=days,
        hi_c=overall_hi,
        lo_c=overall_lo,
        is_wet=is_wet,
        summary=summary,
    )


def _dominant_condition(days: list[DayForecast], overall_hi: float) -> str:
    """Choose one condition for routing. Rain and cold take precedence."""
    buckets = [d.condition for d in days]
    if "rain" in buckets:
        return "rain"
    if overall_hi < _COLD_MAX_C or "cold" in buckets:
        return "cold"
    if "sun" in buckets and overall_hi >= _WARM_MIN_C:
        return "sun"
    if "sun" in buckets:
        return "sun"
    return "mild"


def _summarize(days: list[DayForecast], dominant: str, hi: float, lo: float) -> str:
    parts = ", ".join(f"{d.day} {d.label.lower()} {round(d.hi_c)}/{round(d.lo_c)}°C" for d in days)
    lead = {
        "rain": "Wet and changeable",
        "cold": "Cold across the window",
        "sun": "Warm and clear",
        "mild": "Mild and settled",
    }.get(dominant, "Mixed")
    return f"{lead} (range {round(lo)}-{round(hi)}°C). {parts}."


def _weekday(iso_date: str) -> str:
    """Return a 3-letter weekday for an ISO date string (best-effort)."""
    try:
        import datetime as _dt

        return _dt.date.fromisoformat(iso_date[:10]).strftime("%a").upper()
    except (ValueError, TypeError):
        return (iso_date or "DAY")[:3].upper()


class WeatherAgent:
    """Weather specialist wrapper.

    Primary path is deterministic normalization (:func:`normalize`). The LLM is
    used only for an optional friendlier one-line read; if it fails or no client
    is provided, the deterministic ``summary`` stands in. This keeps the agent
    cheap and never blocks the styling turn on a model call.
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.identity = get_identity("weather")
        self.llm = llm

    def read(
        self,
        *,
        forecast: dict[str, Any] | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ) -> Conditions:
        """Produce structured conditions from a forecast payload or coordinates."""
        if forecast is None:
            if lat is None or lon is None:
                return Conditions(dominant="mild", summary="No location for forecast.")
            forecast = fetch_open_meteo(lat, lon)  # pragma: no cover - network
        conditions = normalize(forecast)
        if self.llm is not None:
            conditions.summary = self._polish(conditions)
        return conditions

    def _polish(self, conditions: Conditions) -> str:
        try:
            content = self.llm.chat(  # type: ignore[union-attr]
                self.identity.route,
                [
                    {
                        "role": "system",
                        "content": "You are a terse weather reader for a clothing "
                        "stylist. One sentence, no emojis, <=20 words.",
                    },
                    {"role": "user", "content": conditions.summary},
                ],
                temperature=0.2,
                max_tokens=60,
            )
            content = content.strip()
            return content or conditions.summary
        except Exception:  # noqa: BLE001 - never block the turn on the model
            return conditions.summary

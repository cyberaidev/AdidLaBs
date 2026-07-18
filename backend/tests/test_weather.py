"""Tests for the weather handler (Open-Meteo 3-day forecast, keyless).

Happy path: a stubbed Open-Meteo payload is reshaped into 3 day chips with
emoji. Error path: an Open-Meteo failure returns 502 (CORS present).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json

import weather
from tests.conftest import assert_cors, http_event, make_urlopen

_OPEN_METEO_OK = {
    "daily": {
        "time": ["2026-07-18", "2026-07-19", "2026-07-20"],
        "weathercode": [0, 61, 3],  # clear, rain, overcast
        "temperature_2m_max": [22.4, 18.1, 16.9],
        "temperature_2m_min": [11.2, 9.8, 8.0],
    }
}

# Open-Meteo can return a null weathercode for a day with only partial data.
# Historically this crashed the handler at int(None) -> TypeError, returning a
# raw 500 with NO CORS headers. This payload is the regression fixture.
_OPEN_METEO_NULL_CODE = {
    "daily": {
        "time": ["2026-07-18", "2026-07-19", "2026-07-20"],
        "weathercode": [0, None, 3],  # middle day has no code (partial data)
        "temperature_2m_max": [22.4, 18.1, 16.9],
        "temperature_2m_min": [11.2, None, 8.0],
    }
}


def test_weather_happy_three_days(monkeypatch):
    """A valid Open-Meteo response yields exactly 3 mapped day chips."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        make_urlopen({"api.open-meteo.com": _OPEN_METEO_OK}),
    )

    resp = weather.handler(http_event("GET", query={"lat": "-33.87", "lon": "151.2"}))

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    days = body["days"]
    assert len(days) == 3
    assert days[0]["emoji"] == "☀️"          # code 0 -> sun
    assert days[1]["label"] == "Light rain"  # code 61
    assert days[0]["hi"] == 22 and days[0]["lo"] == 11
    assert days[0]["day"]  # 3-letter weekday present


def test_weather_tolerates_null_weathercode(monkeypatch):
    """A null weathercode entry must not crash the handler (regression).

    Open-Meteo can return ``weathercode: [0, None, 3]`` on a partial-data day.
    Before the fix, ``int(None)`` raised an uncaught ``TypeError`` -> raw 500
    with no CORS headers and a leaked stack trace. Now the null day maps to the
    default glyph, the response is a clean 200 with CORS, and the emitted
    weathercode is normalised to 0.
    """
    monkeypatch.setattr(
        "urllib.request.urlopen",
        make_urlopen({"api.open-meteo.com": _OPEN_METEO_NULL_CODE}),
    )

    resp = weather.handler(http_event("GET", query={"lat": "-33.87", "lon": "151.2"}))

    assert resp["statusCode"] == 200
    assert_cors(resp)
    days = json.loads(resp["body"])["days"]
    assert len(days) == 3
    # Null-code middle day -> default glyph, weathercode normalised to 0.
    assert days[1]["emoji"] == "⛅"
    assert days[1]["label"] == "Unknown"
    assert days[1]["weathercode"] == 0
    # Null low temperature is still guarded to None (pre-existing behaviour).
    assert days[1]["lo"] is None
    # Neighbouring days with real codes still map correctly.
    assert days[0]["emoji"] == "☀️"
    assert days[2]["label"] == "Overcast"


def test_weather_defaults_to_sydney_when_no_coords(monkeypatch):
    """Missing lat/lon falls back to Sydney coords and still returns 200."""
    captured = {}

    def _fake(req, timeout=None):  # noqa: ARG001
        captured["url"] = req.full_url
        return make_urlopen({"api.open-meteo.com": _OPEN_METEO_OK})(req, timeout)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    resp = weather.handler(http_event("GET", query=None))

    assert resp["statusCode"] == 200
    # Sydney latitude threaded into the upstream request.
    assert "latitude=-33.8688" in captured["url"]


def test_weather_error_upstream_502(monkeypatch):
    """Open-Meteo failure surfaces as a 502 with CORS."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        make_urlopen({"api.open-meteo.com": {}}, error_for="api.open-meteo.com"),
    )
    resp = weather.handler(http_event("GET", query={"lat": "-33.87", "lon": "151.2"}))

    assert resp["statusCode"] == 502
    assert_cors(resp)
    assert json.loads(resp["body"])["error"]


def test_weather_bad_coords_400(monkeypatch):
    """Non-numeric coords are a 400 before any network call."""
    monkeypatch.setattr("urllib.request.urlopen", make_urlopen({}))
    resp = weather.handler(http_event("GET", query={"lat": "abc", "lon": "xyz"}))
    assert resp["statusCode"] == 400
    assert_cors(resp)

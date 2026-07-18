"""Tests for the session handler (server time + IP geolocation).

Happy path: CloudFront viewer headers resolve location with no network call.
Error path: no headers + ip-api failure falls back to Sydney (never raises).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import session
from tests.conftest import assert_cors, http_event, make_urlopen


def test_session_happy_cloudfront_headers(monkeypatch):
    """CloudFront viewer headers populate geo with NO outbound call."""
    # If any network call happens, this urlopen raises -> proves headers win.
    monkeypatch.setattr("urllib.request.urlopen", make_urlopen({}))

    event = http_event(
        "GET",
        headers={
            "cloudfront-viewer-city": "Sydney",
            "cloudfront-viewer-country-region-name": "New South Wales",
            "cloudfront-viewer-country-name": "Australia",
            "cloudfront-viewer-latitude": "-33.8688",
            "cloudfront-viewer-longitude": "151.2093",
            "cloudfront-viewer-time-zone": "Australia/Sydney",
        },
    )
    resp = session.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    import json

    body = json.loads(resp["body"])
    assert body["city"] == "Sydney"
    assert body["geoSource"] == "cloudfront"
    assert body["lat"] == -33.8688
    assert body["region_aws"] == "ap-southeast-2"
    assert "localTime" in body and "serverTimeUtc" in body


def test_session_error_ipapi_down_falls_back(monkeypatch):
    """No CloudFront headers + ip-api failure -> Sydney fallback, still 200."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        make_urlopen({"ip-api.com": {}}, error_for="ip-api.com"),
    )

    resp = session.handler(http_event("GET", headers={}))

    assert resp["statusCode"] == 200
    assert_cors(resp)
    import json

    body = json.loads(resp["body"])
    assert body["geoSource"] == "fallback"
    assert body["city"] == "Sydney"


def test_session_rejects_non_get():
    """A non-GET method is a 405 (still CORS'd)."""
    resp = session.handler(http_event("POST"))
    assert resp["statusCode"] == 405
    assert_cors(resp)


def test_session_options_preflight():
    """OPTIONS returns a 204 preflight with CORS headers."""
    resp = session.handler(http_event("OPTIONS"))
    assert resp["statusCode"] == 204
    assert_cors(resp)

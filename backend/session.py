"""GET /api/session - server time + IP geolocation.

Returns the server clock plus an approximate caller location. Location is
resolved from CloudFront viewer headers first, then the keyless ip-api.com
endpoint, then a Sydney fallback (see ``common.geo``). The frontend uses this
to populate the black weather bar (design Sec. 5.6) and to fetch weather at the
resolved lat/lon - the user is never asked to type a location.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from common.geo import resolve_geo
from common.http import error, get_method, ip_from_headers, lower_headers, preflight, respond


def _local_time(geo: dict[str, Any], now_utc: datetime) -> dict[str, str]:
    """Compute a local time string for the resolved timezone.

    Uses the stdlib ``zoneinfo`` when the tz database is available; otherwise
    falls back to UTC so the endpoint never fails on a missing tzdata package.
    """
    tz_name = geo.get("tz") or "UTC"
    local = now_utc
    resolved_tz = "UTC"
    try:
        from zoneinfo import ZoneInfo

        local = now_utc.astimezone(ZoneInfo(tz_name))
        resolved_tz = tz_name
    except Exception:  # noqa: BLE001 - missing tzdata must not break the demo
        local = now_utc
        resolved_tz = "UTC"
    return {
        "localTime": local.strftime("%H:%M"),
        "localDate": local.strftime("%Y-%m-%d"),
        "tz": resolved_tz,
        "iso": local.isoformat(),
    }


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/session."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    # Normalise header keys ONCE and share the result with both the IP resolver
    # and the geo resolver, instead of each re-lowering the same dict.
    headers = lower_headers(event)
    ip = ip_from_headers(headers, event)
    geo = resolve_geo(headers, ip, headers_lowered=True)

    now_utc = datetime.now(timezone.utc)
    clock = _local_time(geo, now_utc)

    body = {
        "ip": ip,
        "city": geo.get("city"),
        "region": geo.get("region"),
        "country": geo.get("country"),
        "lat": geo.get("lat"),
        "lon": geo.get("lon"),
        "tz": clock["tz"],
        "localTime": clock["localTime"],
        "localDate": clock["localDate"],
        "serverTimeUtc": now_utc.isoformat(),
        "geoSource": geo.get("source"),
        "region_aws": "ap-southeast-2",
    }
    return respond(200, body)

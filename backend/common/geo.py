"""IP geolocation + CloudFront viewer-header helpers.

Resolution strategy (architecture Sec. 1.2, design Sec. 5.6):
  1. Prefer CloudFront viewer headers (``cloudfront-viewer-*``) - free, no
     network call, already attached at the edge.
  2. Fall back to the keyless ip-api.com JSON endpoint for the caller's IP.
  3. Fall back to a Sydney default so the demo weather bar always renders
     (region is ap-southeast-2).

No third-party API key is required on any path.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Mapping

# ap-southeast-2 default (Sydney) - keeps the weather bar populated even when
# both the CloudFront headers and ip-api.com are unavailable.
SYDNEY_FALLBACK: dict[str, Any] = {
    "city": "Sydney",
    "region": "New South Wales",
    "country": "Australia",
    "lat": -33.8688,
    "lon": 151.2093,
    "tz": "Australia/Sydney",
    "source": "fallback",
}

_IP_API_TIMEOUT = 3.0
_IP_API_FIELDS = "status,message,city,regionName,country,lat,lon,timezone,query"


def _from_cloudfront_headers(
    headers: Mapping[str, str], *, already_lower: bool = False
) -> dict[str, Any] | None:
    """Build a geo dict from CloudFront viewer geolocation headers if present.

    CloudFront can forward ``cloudfront-viewer-city``,
    ``cloudfront-viewer-country-region-name``, ``cloudfront-viewer-country-name``,
    ``cloudfront-viewer-latitude``, ``cloudfront-viewer-longitude`` and
    ``cloudfront-viewer-time-zone``. Requires only lat/lon to be useful for the
    weather lookup.

    Pass ``already_lower=True`` when ``headers`` keys are known to be
    lower-cased (e.g. via ``common.http.lower_headers``) to skip a redundant
    re-lowering of the same dict.
    """
    lower = headers if already_lower else {k.lower(): v for k, v in headers.items()}
    lat = lower.get("cloudfront-viewer-latitude")
    lon = lower.get("cloudfront-viewer-longitude")
    if not lat or not lon:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    return {
        "city": lower.get("cloudfront-viewer-city") or "Unknown",
        "region": lower.get("cloudfront-viewer-country-region-name")
        or lower.get("cloudfront-viewer-country-region")
        or "",
        "country": lower.get("cloudfront-viewer-country-name")
        or lower.get("cloudfront-viewer-country")
        or "",
        "lat": lat_f,
        "lon": lon_f,
        "tz": lower.get("cloudfront-viewer-time-zone") or SYDNEY_FALLBACK["tz"],
        "source": "cloudfront",
    }


def _from_ip_api(ip: str | None) -> dict[str, Any] | None:
    """Resolve geolocation via the keyless ip-api.com endpoint.

    Passing an empty path (``/json/``) lets ip-api resolve the caller's own IP,
    which is what happens when the Lambda has no better source IP.
    """
    path = ip or ""
    url = f"http://ip-api.com/json/{path}?fields={_IP_API_FIELDS}"
    req = urllib.request.Request(url, headers={"User-Agent": "AdidLaBs/1.0"})
    with urllib.request.urlopen(req, timeout=_IP_API_TIMEOUT) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "success":
        return None
    return {
        "city": data.get("city") or "Unknown",
        "region": data.get("regionName") or "",
        "country": data.get("country") or "",
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "tz": data.get("timezone") or SYDNEY_FALLBACK["tz"],
        "source": "ip-api",
    }


def resolve_geo(
    headers: Mapping[str, str], ip: str | None, *, headers_lowered: bool = False
) -> dict[str, Any]:
    """Resolve an approximate location, preferring CloudFront headers.

    Never raises: any failure falls through to the Sydney default so the
    weather bar always has coordinates to render.

    Pass ``headers_lowered=True`` when ``headers`` keys were already normalised
    (e.g. by ``common.http.lower_headers``) so the CloudFront lookup doesn't
    re-lower the same dict a second time.
    """
    cf = _from_cloudfront_headers(headers, already_lower=headers_lowered)
    if cf:
        return cf
    try:
        api = _from_ip_api(ip)
        if api and api.get("lat") is not None and api.get("lon") is not None:
            return api
    except Exception:  # noqa: BLE001 - geolocation is best-effort by design
        pass
    return dict(SYDNEY_FALLBACK)

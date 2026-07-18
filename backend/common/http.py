"""HTTP helpers shared by every AdidLaBs Lambda handler.

Provides CORS headers, JSON response builders, request-body parsing, and the
authenticated ``user_id`` extractor. Every response returned by a handler MUST
flow through :func:`respond` (or :func:`error`) so CORS headers are always
present - reviewers verify this.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

# Allowed methods advertised on every response / preflight. The HTTP API routes
# only expose the verbs each handler supports, but we advertise the full set so
# a single CORS config works across all routes.
_ALLOWED_METHODS = "GET,POST,DELETE,OPTIONS"
_ALLOWED_HEADERS = "Content-Type,Authorization,X-Forwarded-For"

# Anonymous fallback identity used only when no JWT claim is present (e.g.
# DEMO_MODE with no authorizer wired). Real deployments derive user_id from the
# Cognito JWT ``sub`` claim, never from the request body (see architecture Sec. 6).
DEMO_USER_ID = "demo-user"


def cors_headers() -> dict[str, str]:
    """Return the CORS + content-type headers attached to every response.

    ``CORS_ALLOW_ORIGIN`` may pin a specific CloudFront origin; it defaults to
    ``*`` for the demo (the site stays on the raw CloudFront domain).
    """
    origin = os.environ.get("CORS_ALLOW_ORIGIN", "*")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": _ALLOWED_METHODS,
        "Access-Control-Allow-Headers": _ALLOWED_HEADERS,
        "Access-Control-Max-Age": "3600",
    }


def respond(status: int, body: Any) -> dict[str, Any]:
    """Build an API Gateway (HTTP API v2) proxy response with CORS headers."""
    return {
        "statusCode": status,
        "headers": cors_headers(),
        "body": json.dumps(body, default=str),
    }


def error(status: int, message: str, **extra: Any) -> dict[str, Any]:
    """Build a JSON error response (CORS included)."""
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return respond(status, payload)


def preflight() -> dict[str, Any]:
    """Response for an OPTIONS CORS preflight request (empty body)."""
    return {"statusCode": 204, "headers": cors_headers(), "body": ""}


def get_method(event: Mapping[str, Any]) -> str:
    """Extract the HTTP method from an HTTP API v2 (or REST v1) event."""
    ctx = event.get("requestContext") or {}
    http = ctx.get("http") or {}
    method = http.get("method") or event.get("httpMethod")
    return (method or "GET").upper()


def parse_body(event: Mapping[str, Any]) -> dict[str, Any]:
    """Parse a JSON request body, tolerating base64 encoding and empties.

    Returns an empty dict when there is no body. Raises ``ValueError`` on
    malformed JSON so handlers can turn it into a 400.
    """
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("request body must be a JSON object")
    return parsed


def get_query(event: Mapping[str, Any]) -> dict[str, str]:
    """Return query-string parameters as a plain dict (never None)."""
    return dict(event.get("queryStringParameters") or {})


def lower_headers(event: Mapping[str, Any]) -> dict[str, str]:
    """Return the event's headers with keys lower-cased exactly once.

    HTTP header names are case-insensitive, and callers that need both the
    client IP (:func:`ip_from_headers`) and CloudFront geo headers should
    normalise once and share the result rather than each re-lowercasing the
    same dict (see ``session.handler``).
    """
    return {k.lower(): v for k, v in (event.get("headers") or {}).items()}


def get_user_id(event: Mapping[str, Any]) -> str:
    """Derive the authenticated user_id from the JWT ``sub`` claim.

    The HTTP API JWT authorizer places verified claims under
    ``requestContext.authorizer.jwt.claims``. We ONLY trust that path - never
    the request body (architecture Sec. 6). Falls back to ``DEMO_USER_ID`` when
    no authorizer is wired, which is the DEMO_MODE / local path.
    """
    ctx = event.get("requestContext") or {}
    authorizer = ctx.get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims") or {}
    sub = claims.get("sub")
    if sub:
        return str(sub)
    return DEMO_USER_ID


def ip_from_headers(headers: Mapping[str, str], event: Mapping[str, Any]) -> str | None:
    """Resolve the client IP from ALREADY lower-cased headers + the event.

    Splitting the header lookup from the (case-insensitive) re-lowering lets
    ``session.handler`` normalise the header map once with :func:`lower_headers`
    and share it with :func:`common.geo.resolve_geo` instead of each pass
    re-lowering the same dict.

    Order of preference (most trustworthy first):
      1. CloudFront viewer header ``cloudfront-viewer-address`` (host:port).
      2. ``X-Forwarded-For`` first hop.
      3. HTTP API request-context source IP.
    """
    viewer = headers.get("cloudfront-viewer-address")
    if viewer:
        # Format is "IP:PORT" (or "[v6]:PORT"); strip the trailing port.
        addr = viewer.rsplit(":", 1)[0]
        return addr.strip("[]") or None

    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None

    ctx = event.get("requestContext") or {}
    http = ctx.get("http") or {}
    return http.get("sourceIp") or ctx.get("identity", {}).get("sourceIp")

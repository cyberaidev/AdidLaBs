"""Shared pytest fixtures and helpers for the AdidLaBs backend suite.

Guarantees ZERO real network calls: ip-api.com, Open-Meteo, boto3/DynamoDB, and
AgentCore are all stubbed. ``urllib.request.urlopen`` is patched per-test via the
``fake_urlopen`` fixture; boto3 clients use botocore's ``Stubber``.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure backend/ is importable so `import session`, `import common.http`, etc.
# resolve exactly as they do inside the Lambda package.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    """Set deterministic env for every test and block accidental region drift."""
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    monkeypatch.setenv("CATALOG_TABLE", "adidlabs-catalog")
    monkeypatch.setenv("BAG_TABLE", "adidlabs-bag")
    # Provide dummy credentials so boto3 client construction never reaches disk.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    # Default to demo mode off / no ARN unless a test opts in.
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("AGENTCORE_AGENT_ARN", raising=False)


class _FakeHTTPResponse(io.BytesIO):
    """Minimal context-manager stand-in for an ``http.client`` response."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def make_urlopen(payloads: dict[str, Any], *, error_for: str | None = None):
    """Build a fake ``urlopen`` that matches by substring in the request URL.

    ``payloads`` maps a URL substring -> JSON-serializable body. If a request
    URL contains ``error_for`` (substring), the fake raises to simulate an
    upstream failure. Any unmatched URL raises AssertionError - this is how we
    prove no unexpected network egress happens.
    """

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001 - signature parity
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if error_for and error_for in url:
            raise OSError(f"simulated upstream failure for {url}")
        for needle, body in payloads.items():
            if needle in url:
                return _FakeHTTPResponse(json.dumps(body).encode("utf-8"))
        raise AssertionError(f"unexpected network call to {url}")

    return _fake_urlopen


def http_event(
    method: str,
    *,
    body: Any = None,
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    sub: str | None = None,
    source_ip: str = "203.0.113.7",
) -> dict[str, Any]:
    """Construct an API Gateway HTTP API v2 proxy event.

    When ``sub`` is provided it is injected as a verified JWT claim so
    ``get_user_id`` returns it.
    """
    authorizer = {"jwt": {"claims": {"sub": sub}}} if sub else {}
    return {
        "requestContext": {
            "http": {"method": method, "sourceIp": source_ip},
            "authorizer": authorizer,
        },
        "headers": headers or {},
        "queryStringParameters": query,
        "body": json.dumps(body) if isinstance(body, (dict, list)) else body,
        "isBase64Encoded": False,
    }


def assert_cors(resp: dict[str, Any]) -> None:
    """Assert a handler response carries the required CORS headers."""
    headers = resp.get("headers") or {}
    assert headers.get("Access-Control-Allow-Origin") is not None
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")
    assert "Authorization" in headers.get("Access-Control-Allow-Headers", "")

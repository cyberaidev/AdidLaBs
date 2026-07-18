"""Tests for the agents roster handler.

Happy path: GET returns all 8 agents with verbatim wids and correct routes.
Error path: a non-GET method is a 405. Status flips to running when authed=1.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json

import agents
from tests.conftest import assert_cors, http_event

_EXPECTED_WIDS = {
    "adidlabs/orchestrator-9f21": "nova-pro",
    "adidlabs/weather-3b7c": "haiku-4.5",
    "adidlabs/shoes-4e2a": "haiku-4.5",
    "adidlabs/pants-8c1d": "haiku-4.5",
    "adidlabs/tshirt-2a9e": "haiku-4.5",
    "adidlabs/jumper-6d3f": "haiku-4.5",
    "adidlabs/jacket-1e8b": "haiku-4.5",
    "adidlabs/accessory-5c4a": "haiku-4.5",
}


def test_agents_happy_full_roster():
    """GET returns the exact 8-agent roster, ordering and routes intact."""
    resp = agents.handler(http_event("GET"))

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["count"] == 8
    assert body["region"] == "ap-southeast-2"

    roster = body["agents"]
    assert roster[0]["name"] == "ORCHESTRATOR"  # orchestrator first
    assert roster[1]["name"] == "WEATHER"       # weather second
    for agent in roster:
        assert _EXPECTED_WIDS[agent["wid"]] == agent["route"]
    # Only the orchestrator is nova-pro.
    assert [a["route"] for a in roster].count("nova-pro") == 1
    # Pre-auth default is standby.
    assert all(a["status"] == "standby" for a in roster)


def test_agents_running_when_authed():
    """authed=1 flips every agent to running."""
    resp = agents.handler(http_event("GET", query={"authed": "1"}))
    body = json.loads(resp["body"])
    assert all(a["status"] == "running" for a in body["agents"])


def test_agents_error_non_get_405():
    """A non-GET method is a 405 with CORS."""
    resp = agents.handler(http_event("DELETE"))
    assert resp["statusCode"] == 405
    assert_cors(resp)


def test_agents_options_preflight():
    """OPTIONS returns a 204 preflight."""
    resp = agents.handler(http_event("OPTIONS"))
    assert resp["statusCode"] == 204
    assert_cors(resp)

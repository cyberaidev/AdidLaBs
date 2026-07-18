"""Tests for the chat handler (DEMO_MODE canned reply + AgentCore live path).

Happy path (demo): DEMO_MODE=1 returns a convincing, weather-matched stylist
reply with picks and the real wid roster - no model/network call.
Live path: AgentCore ``invoke_agent_runtime`` is stubbed and relayed.
Error path: a missing message is a 400.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json

import boto3
from botocore.stub import ANY, Stubber

import chat
from tests.conftest import assert_cors, http_event

_SESSION_CTX = {
    "city": "Sydney",
    "region": "New South Wales",
    "weather": {
        "days": [
            {"day": "SAT", "label": "Light rain", "hi": 15, "lo": 7},
            {"day": "SUN", "label": "Overcast", "hi": 16, "lo": 8},
            {"day": "MON", "label": "Clear", "hi": 18, "lo": 9},
        ]
    },
}


def test_chat_demo_mode_canned_reply(monkeypatch):
    """DEMO_MODE=1 yields a grounded canned reply with picks + wid roster."""
    monkeypatch.setenv("DEMO_MODE", "1")

    event = http_event(
        "POST",
        sub="user-123",
        body={"message": "what should I wear this weekend?", "session": _SESSION_CTX},
    )
    resp = chat.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["mode"] == "demo"
    # Weather-aware: cold + wet forecast should surface the shell jacket + rain gear.
    assert "Sydney" in body["reply"]
    assert any(p["category"] == "JACKET" for p in body["picks"])
    assert any(p["category"] == "SHOES" and "Trail" in p["title"] for p in body["picks"])
    # Exactly the eight-agent roster with verbatim wids.
    wids = {a["wid"] for a in body["agents"]}
    assert "adidlabs/orchestrator-9f21" in wids
    assert "adidlabs/accessory-5c4a" in wids
    assert len(body["agents"]) == 8
    # A deal pick carries the struck price fields for the red-price UI.
    deal = next(p for p in body["picks"] if p.get("deal"))
    assert deal["original_price"] > deal["price"]


def test_chat_demo_mode_when_arn_unset(monkeypatch):
    """No DEMO_MODE and no ARN also takes the demo path (site works pre-deploy)."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("AGENTCORE_AGENT_ARN", raising=False)

    resp = chat.handler(http_event("POST", sub="u", body={"message": "hi", "session": {}}))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["mode"] == "demo"


def test_chat_live_path_invokes_runtime(monkeypatch):
    """DEMO_MODE=0 + ARN set invokes AgentCore and relays its reply."""
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv(
        "AGENTCORE_AGENT_ARN",
        "arn:aws:bedrock-agentcore:ap-southeast-2:123456789012:runtime/adidlabs",
    )

    # A realistic Cognito ``sub`` is a 36-char UUID, which satisfies the
    # AgentCore runtimeSessionId >= 33-char rule (chat._session_id passes it
    # through unchanged).
    sub = "11111111-2222-3333-4444-555555555555"

    client = boto3.client("bedrock-agentcore", region_name="ap-southeast-2")
    stubber = Stubber(client)
    runtime_reply = {"reply": "Live stylist here.", "picks": []}
    stubber.add_response(
        "invoke_agent_runtime",
        {
            "runtimeSessionId": sub,
            "contentType": "application/json",
            "response": json.dumps(runtime_reply).encode("utf-8"),
        },
        expected_params={
            "agentRuntimeArn": ANY,
            "runtimeSessionId": sub,
            "payload": ANY,
            "contentType": "application/json",
            "accept": "application/json",
        },
    )
    monkeypatch.setattr(chat.boto3, "client", lambda *a, **k: client)

    with stubber:
        resp = chat.handler(
            http_event("POST", sub=sub, body={"message": "dress me", "session": {}})
        )

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["mode"] == "live"
    assert body["reply"] == "Live stylist here."


def test_chat_live_path_falls_back_on_error(monkeypatch):
    """A runtime failure degrades to a canned reply flagged demo-fallback."""
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv(
        "AGENTCORE_AGENT_ARN",
        "arn:aws:bedrock-agentcore:ap-southeast-2:123456789012:runtime/adidlabs",
    )

    client = boto3.client("bedrock-agentcore", region_name="ap-southeast-2")
    stubber = Stubber(client)
    stubber.add_client_error("invoke_agent_runtime", service_error_code="ThrottlingException")
    monkeypatch.setattr(chat.boto3, "client", lambda *a, **k: client)

    with stubber:
        resp = chat.handler(
            http_event("POST", sub="user-123", body={"message": "dress me", "session": _SESSION_CTX})
        )

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["mode"] == "demo-fallback"
    assert "runtimeError" in body
    assert body["picks"]  # canned picks still present so the drawer renders


def test_chat_missing_message_400(monkeypatch):
    """A blank message is a 400 with CORS."""
    monkeypatch.setenv("DEMO_MODE", "1")
    resp = chat.handler(http_event("POST", sub="u", body={"message": "   "}))
    assert resp["statusCode"] == 400
    assert_cors(resp)


def test_chat_rejects_get(monkeypatch):
    """GET is not allowed on /api/chat."""
    monkeypatch.setenv("DEMO_MODE", "1")
    resp = chat.handler(http_event("GET"))
    assert resp["statusCode"] == 405
    assert_cors(resp)


def test_chat_session_id_meets_agentcore_min_length():
    """_session_id always returns a >= 33-char id (AgentCore constraint).

    Short/anonymous ids are expanded; a full-length UUID sub passes through.
    """
    short = chat._session_id("demo-user")
    assert len(short) >= 33
    assert short.startswith("demo-user-")
    uuid_sub = "11111111-2222-3333-4444-555555555555"
    assert chat._session_id(uuid_sub) == uuid_sub  # already long enough
    # Deterministic: same input -> same session id (multi-turn continuity).
    assert chat._session_id("demo-user") == short

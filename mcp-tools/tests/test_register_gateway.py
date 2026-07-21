"""Tests for gateway + target registration.

Concept demo - no affiliation with adidas AG. All products fictional.

No real AgentCore control-plane calls - the boto3 clients are stubbed.
"""

from __future__ import annotations

import pytest


class FakeGatewayClient:
    """Stub of the bedrock-agentcore-control client used by register_gateway."""

    def __init__(self, gateways=None, targets=None):
        self.gateways = gateways or []
        self.targets = targets or []
        self.created_targets = []

    def get_paginator(self, op):
        assert op == "list_gateways"
        gateways = self.gateways

        class _P:
            def paginate(self):
                yield {"items": gateways}

        return _P()

    def get_gateway(self, gatewayIdentifier):
        return {"gatewayId": gatewayIdentifier, "gatewayUrl": f"https://{gatewayIdentifier}.example"}

    def list_gateway_targets(self, gatewayIdentifier):
        return {"items": self.targets}

    def create_gateway_target(self, **payload):
        self.created_targets.append(payload)
        return {"targetId": "tgt-1"}


@pytest.fixture
def reg():
    import register_gateway as rg
    return rg


def test_tool_entries_cover_all_six_tools(reg):
    entries = [reg.build_tool_entry(s) for s in reg.TOOL_SPECS]
    assert [e["name"] for e in entries] == [
        "get_catalog",
        "get_deals",
        "bag_add",
        "bag_get",
        "search_lab_knowledge",
        "search_web",
    ]
    # Every entry carries a JSON schema with a properties object.
    for entry in entries:
        assert entry["inputSchema"]["type"] == "object"
        assert "properties" in entry["inputSchema"]


def test_target_payload_shape(reg):
    payload = reg.build_target_payload("gw-1", "arn:aws:lambda:x:1:function:tools")
    assert payload["gatewayIdentifier"] == "gw-1"
    assert payload["name"] == reg.TARGET_NAME
    lam = payload["targetConfiguration"]["mcp"]["lambda"]
    assert lam["lambdaArn"] == "arn:aws:lambda:x:1:function:tools"
    assert len(lam["toolSchema"]["inlinePayload"]) == 6
    assert payload["credentialProviderConfigurations"][0]["credentialProviderType"] == "GATEWAY_IAM_ROLE"


def test_ensure_target_reuses_existing(reg):
    fake = FakeGatewayClient(targets=[{"name": reg.TARGET_NAME, "targetId": "tgt-existing"}])
    tid = reg.ensure_target(fake, "gw-1", "arn:aws:lambda:x:1:function:tools")
    assert tid == "tgt-existing"
    assert fake.created_targets == []


def test_ensure_target_creates_when_missing(reg):
    fake = FakeGatewayClient(targets=[])
    tid = reg.ensure_target(fake, "gw-1", "arn:aws:lambda:x:1:function:tools")
    assert tid == "tgt-1"
    assert len(fake.created_targets) == 1
    assert fake.created_targets[0]["gatewayIdentifier"] == "gw-1"


def test_find_gateway_by_name(reg):
    fake = FakeGatewayClient(gateways=[{"name": reg.GATEWAY_NAME, "gatewayId": "gw-9"}])
    found = reg.find_gateway_by_name(fake, reg.GATEWAY_NAME)
    assert found["gatewayId"] == "gw-9"
    assert reg.find_gateway_by_name(fake, "nope") is None


def test_resolve_gateway_id_precedence(reg, monkeypatch):
    monkeypatch.setenv("AGENTCORE_GATEWAY_ID", "env-gw")
    assert reg._resolve_gateway_id("flag-gw") == "flag-gw"
    assert reg._resolve_gateway_id(None) == "env-gw"
    monkeypatch.delenv("AGENTCORE_GATEWAY_ID", raising=False)
    monkeypatch.delenv("GATEWAY_ID", raising=False)
    assert reg._resolve_gateway_id(None) is None


def test_dry_run_calls_no_aws(reg, monkeypatch, capsys):
    def boom():
        raise AssertionError("no AWS client may be created on dry-run")

    monkeypatch.setattr(reg, "_gateway_client", boom)
    monkeypatch.setattr(reg, "_iam_client", boom)
    monkeypatch.setattr(reg, "_lambda_client", boom)
    assert reg.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "planned" in out and "search_web" in out

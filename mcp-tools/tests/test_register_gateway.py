"""Tests for gateway target registration.

Concept demo - no affiliation with adidas AG. All products fictional.

No real AgentCore control-plane calls - the boto3 client is stubbed.
"""

from __future__ import annotations

import pytest


class FakeGatewayClient:
    def __init__(self, fail_for=None):
        self.created = []
        self._fail_for = fail_for or set()

    def create_gateway_target(self, **payload):
        name = payload["name"]
        if name in self._fail_for:
            raise RuntimeError(f"conflict registering {name}")
        self.created.append(payload)
        return {"targetId": f"tgt-{name}"}


@pytest.fixture
def reg(monkeypatch):
    import register_gateway as rg
    return rg


def test_registers_all_six_tools(reg, monkeypatch):
    fake = FakeGatewayClient()
    monkeypatch.setattr(reg, "_gateway_client", lambda: fake)

    results = reg.register_all("adidlabs-tools-gw", dry_run=False)

    # Every tool from the canonical registry is registered exactly once.
    tool_names = [r["tool"] for r in results]
    assert tool_names == [
        "get_catalog",
        "get_deals",
        "bag_add",
        "bag_get",
        "search_lab_knowledge",
        "search_web",
    ]
    assert all(r["status"] == "registered" for r in results)
    assert len(fake.created) == 6

    # Each target carries the gateway id, an MCP endpoint, and a backend tag.
    first = fake.created[0]
    assert first["gatewayIdentifier"] == "adidlabs-tools-gw"
    assert first["targetConfiguration"]["mcp"]["toolName"] == "get_catalog"
    assert first["tags"]["project"] == "adidlabs"


def test_dry_run_calls_no_aws(reg, monkeypatch):
    def boom():
        raise AssertionError("boto3 client must not be created on dry-run")

    monkeypatch.setattr(reg, "_gateway_client", boom)
    results = reg.register_all("gw", dry_run=True)
    assert len(results) == 6
    assert all(r["status"] == "planned" for r in results)
    # Payloads are still fully built for inspection.
    assert results[0]["payload"]["name"] == "get_catalog"


def test_partial_failure_reported_per_tool(reg, monkeypatch):
    fake = FakeGatewayClient(fail_for={"search_web"})
    monkeypatch.setattr(reg, "_gateway_client", lambda: fake)

    results = reg.register_all("gw", dry_run=False)
    statuses = {r["tool"]: r["status"] for r in results}
    assert statuses["search_web"] == "error"
    # The other five still registered - one failure does not abort the batch.
    assert sum(1 for s in statuses.values() if s == "registered") == 5


def test_main_exit_code_nonzero_on_error(reg, monkeypatch, capsys):
    fake = FakeGatewayClient(fail_for={"get_deals"})
    monkeypatch.setattr(reg, "_gateway_client", lambda: fake)
    monkeypatch.setattr(reg, "_resolve_gateway_id", lambda explicit: "gw-x")

    code = reg.main([])
    assert code == 1
    out = capsys.readouterr().out
    assert "gw-x" in out


def test_resolve_gateway_id_precedence(reg, monkeypatch):
    monkeypatch.setenv("AGENTCORE_GATEWAY_ID", "env-gw")
    # Explicit flag wins over env.
    assert reg._resolve_gateway_id("flag-gw") == "flag-gw"
    # Env used when no flag.
    assert reg._resolve_gateway_id(None) == "env-gw"


def test_target_payload_shape(reg):
    spec = {"name": "get_catalog", "description": "desc", "backend": "dynamodb:adidlabs-catalog"}
    payload = reg.build_target_payload("gw-1", spec)
    assert payload["name"] == "get_catalog"
    assert payload["targetConfiguration"]["mcp"]["endpoint"] == reg.MCP_SERVER_ENDPOINT
    assert payload["tags"]["backend"] == "dynamodb:adidlabs-catalog"

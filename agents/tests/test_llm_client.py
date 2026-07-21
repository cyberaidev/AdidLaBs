"""LLM client contract: route validation + lenient JSON parsing.

No network - these exercise pure validation/parsing paths only.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import pytest

from agents.common.llm import (
    ALLOWED_ROUTES,
    ROUTE_HAIKU,
    ROUTE_NOVA_PRO,
    ROUTE_TARGETS,
    LLMClient,
    LLMError,
    resolve_route,
    _loads_lenient,
)


def test_allowed_routes_are_exactly_two():
    assert ALLOWED_ROUTES == {ROUTE_NOVA_PRO, ROUTE_HAIKU}


def test_resolve_route_accepts_allowed():
    assert resolve_route("nova-pro") == "nova-pro"
    assert resolve_route("haiku-4.5") == "haiku-4.5"


def test_resolve_route_rejects_raw_model_id():
    with pytest.raises(ValueError):
        resolve_route("apac.amazon.nova-pro-v1:0")


def test_route_targets_map_to_geo_profiles():
    assert ROUTE_TARGETS[ROUTE_NOVA_PRO] == "bedrock/apac.amazon.nova-pro-v1:0"
    assert ROUTE_TARGETS[ROUTE_HAIKU] == (
        "bedrock/au.anthropic.claude-haiku-4-5-20251001-v1:0"
    )


def test_chat_without_base_url_raises():
    client = LLMClient(base_url="")
    with pytest.raises(LLMError):
        client.chat("nova-pro", [{"role": "user", "content": "hi"}])


def test_lenient_json_recovers_wrapped_object():
    assert _loads_lenient('here you go: {"a": 1} thanks') == {"a": 1}


def test_lenient_json_plain():
    assert _loads_lenient('{"ok": true}') == {"ok": True}


def test_lenient_json_empty_raises():
    with pytest.raises(LLMError):
        _loads_lenient("   ")

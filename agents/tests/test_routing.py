"""Routing contract tests: rain -> jacket+accessory, sun -> tshirt+shoes.

These are the load-bearing tests for the supervisor. They run the full graph
with a MOCKED LLM (see conftest.MockLLMClient) and the in-process LocalToolClient,
so no live Bedrock call ever happens in CI.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from agents.common.tools import LocalToolClient
from agents.orchestrator import build_orchestrator, route_for_conditions
from agents.weather_agent import normalize


# ---- pure routing rule -----------------------------------------------------
def test_route_rule_rain():
    assert route_for_conditions("rain") == ["jacket", "accessory"]


def test_route_rule_sun():
    assert route_for_conditions("sun") == ["tshirt", "shoes"]


def test_route_rule_unknown_defaults_to_mild():
    assert route_for_conditions("hurricane") == route_for_conditions("mild")


# ---- weather normalization classifies the fixtures correctly ---------------
def test_rain_forecast_is_rain(rain_forecast):
    assert normalize(rain_forecast).dominant == "rain"


def test_sun_forecast_is_sun(sun_forecast):
    assert normalize(sun_forecast).dominant == "sun"


# ---- full graph, mocked LLM: rain -> jacket + accessory --------------------
def test_supervisor_routes_rain_to_jacket_and_accessory(mock_llm, rain_forecast):
    orch = build_orchestrator(tools=LocalToolClient(), llm=mock_llm)
    state = orch.run("what should I wear today?", forecast=rain_forecast)

    assert state["conditions"]["dominant"] == "rain"
    assert "jacket" in state["routed"]
    assert "accessory" in state["routed"]
    # The mandated categories lead the routed list.
    assert state["routed"][:2] == ["jacket", "accessory"]

    picked_agents = {r["agent"] for r in state["results"] if r["status"] == "ok"}
    assert "adidlabs/jacket-1e8b" in picked_agents
    assert "adidlabs/accessory-5c4a" in picked_agents
    assert state["reply"]  # a non-empty stylist reply was composed


# ---- full graph, mocked LLM: sun -> tshirt + shoes -------------------------
def test_supervisor_routes_sun_to_tshirt_and_shoes(mock_llm, sun_forecast):
    orch = build_orchestrator(tools=LocalToolClient(), llm=mock_llm)
    state = orch.run("dress me for the weekend", forecast=sun_forecast)

    assert state["conditions"]["dominant"] == "sun"
    assert "tshirt" in state["routed"]
    assert "shoes" in state["routed"]
    assert state["routed"][:2] == ["tshirt", "shoes"]

    picked_agents = {r["agent"] for r in state["results"] if r["status"] == "ok"}
    assert "adidlabs/tshirt-2a9e" in picked_agents
    assert "adidlabs/shoes-4e2a" in picked_agents


# ---- only allowed routes are ever used (no raw model ids) ------------------
def test_only_allowed_routes_used(mock_llm, rain_forecast):
    orch = build_orchestrator(tools=LocalToolClient(), llm=mock_llm)
    orch.run("what should I wear?", forecast=rain_forecast)
    # Orchestrator uses nova-pro; specialists use haiku-4.5. Nothing else.
    assert mock_llm.routes_used().issubset({"nova-pro", "haiku-4.5"})
    assert "nova-pro" in mock_llm.routes_used()


# ---- user can widen routing but never shrink the mandated set --------------
def test_user_request_widens_but_keeps_mandated(mock_llm, sun_forecast):
    orch = build_orchestrator(tools=LocalToolClient(), llm=mock_llm)
    state = orch.run("I also want a jacket please", forecast=sun_forecast)
    assert "tshirt" in state["routed"] and "shoes" in state["routed"]
    assert "jacket" in state["routed"]  # widened by explicit request

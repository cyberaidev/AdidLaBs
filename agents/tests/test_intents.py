"""Tests for shopper weather-intent handling (snow/rain/heat asks).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from agents.orchestrator import Orchestrator
from agents.weather_agent import intent_override


def test_intent_override_detects_conditions():
    assert intent_override("any snow options?") == ("cold", "snow")
    assert intent_override("I am going skiing next week") == ("cold", "snow")
    assert intent_override("something for the rain please") == ("rain", "rain")
    assert intent_override("beach heat looks") == ("sun", "heat and sun")
    assert intent_override("what should I wear") is None


def test_snow_ask_overrides_a_sunny_forecast():
    orch = Orchestrator(llm=None)
    sunny = {"daily": {"time": ["2026-07-21"], "weathercode": [0],
                       "temperature_2m_max": [31.0], "temperature_2m_min": [22.0]}}
    out = orch.run("any snow options?", forecast=sunny)
    assert out["conditions"]["dominant"] == "cold"
    assert out["conditions"]["requested"] == "snow"
    # Mandated cold routing plus the snow widening (boots + accessories).
    for cat in ("jumper", "jacket", "shoes", "accessory"):
        assert cat in out["routed"]
    assert "snow" in out["reply"].lower()


def test_message_keywords_rerank_candidates():
    from agents.common.tools import LocalToolClient
    from agents.shopping_agents import build_shopping_agents

    items = [
        {"item_id": "s1", "category": "shoes", "title": "Court Classic",
         "price": 80.0, "deal_pct": 0},
        {"item_id": "s2", "category": "shoes", "title": "Winter Thermal Boot",
         "price": 120.0, "deal_pct": 0},
    ]
    agent = build_shopping_agents(LocalToolClient(items=items), None)["shoes"]
    # A snow ask must outrank the default ordering with the winter boot.
    ranked = agent._candidates("boot for snow", {"dominant": "cold", "requested": "snow"})
    assert ranked[0]["item_id"] == "s2"
    # No ask -> both candidates still present.
    default = agent._candidates("", {"dominant": "mild"})
    assert {i["item_id"] for i in default} == {"s1", "s2"}


def test_same_ask_is_deterministic():
    orch = Orchestrator(llm=None)
    agent = orch.specialists["jacket"]
    a = [i["item_id"] for i in agent._candidates("snow", {"dominant": "cold", "requested": "snow"})]
    b = [i["item_id"] for i in agent._candidates("snow", {"dominant": "cold", "requested": "snow"})]
    assert a == b

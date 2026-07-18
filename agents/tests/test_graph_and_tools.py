"""Graph compilation, entrypoint, KB-miss fallback, and A2A/roster contract.

All hermetic - MockLLMClient + LocalToolClient, no network.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from agents.common.a2a import TaskEnvelope, TaskResult, make_task
from agents.common.roster import ROSTER, roster_public
from agents.common.tools import LocalToolClient, kb_is_useful
from agents.orchestrator import build_orchestrator
from agents.shopping_agents import build_shopping_agents


# ---- graph compiles --------------------------------------------------------
def test_graph_compiles(mock_llm):
    orch = build_orchestrator(tools=LocalToolClient(), llm=mock_llm)
    compiled = orch.compile()
    assert compiled is not None
    assert hasattr(compiled, "invoke")


# ---- entrypoint loads and handles a turn -----------------------------------
def test_entrypoint_handle_rain(rain_forecast):
    from agents import entrypoint

    out = entrypoint.handle({"message": "what should I wear?", "forecast": rain_forecast})
    assert out["agent"] == "adidlabs/orchestrator-9f21"
    assert "jacket" in out["routed"] and "accessory" in out["routed"]
    assert isinstance(out["picks"], list)
    assert out["reply"]


def test_entrypoint_empty_message():
    from agents import entrypoint

    out = entrypoint.handle({"message": ""})
    assert out["routed"] == []
    assert out["reply"]


# ---- KB-miss -> web fallback ----------------------------------------------
def test_kb_useful_gate():
    assert kb_is_useful([{"score": 0.9}]) is True
    assert kb_is_useful([{"score": 0.1}]) is False
    assert kb_is_useful([]) is False


def test_specialist_falls_back_to_web_on_kb_miss(mock_llm):
    tools = LocalToolClient()
    agents = build_shopping_agents(tools, mock_llm)
    jacket = agents["jacket"]
    # "mild" conditions + an off-topic message won't match the rain/sun/cold KB
    # keywords, forcing the web fallback path.
    env = make_task(
        sender="adidlabs/orchestrator-9f21",
        recipient=jacket.identity.wid,
        payload={"conditions": {"dominant": "mild"}, "user_message": "zzz"},
    )
    result = jacket.handle(env)
    assert result.status == "ok"
    # Web citations carry a url; KB citations carry a source.
    assert result.citations and all("url" in c for c in result.citations)


def test_specialist_uses_kb_when_relevant(mock_llm):
    tools = LocalToolClient()
    agents = build_shopping_agents(tools, mock_llm)
    jacket = agents["jacket"]
    env = make_task(
        sender="adidlabs/orchestrator-9f21",
        recipient=jacket.identity.wid,
        payload={"conditions": {"dominant": "rain"}, "user_message": "rain jacket"},
    )
    result = jacket.handle(env)
    assert result.status == "ok"
    assert result.citations and all("source" in c for c in result.citations)


# ---- A2A envelope round-trips ---------------------------------------------
def test_a2a_envelope_roundtrip():
    env = make_task(sender="a/b", recipient="c/d", payload={"x": 1})
    rebuilt = TaskEnvelope.from_dict(env.to_dict())
    assert rebuilt.task_id == env.task_id
    assert rebuilt.recipient == "c/d"
    assert rebuilt.payload == {"x": 1}


def test_a2a_result_roundtrip():
    res = TaskResult(task_id="t1", agent="a/b", rationale="ok", picks=[{"item_id": "x"}])
    rebuilt = TaskResult.from_dict(res.to_dict())
    assert rebuilt.task_id == "t1"
    assert rebuilt.picks == [{"item_id": "x"}]


# ---- roster contract (wids + routes rendered verbatim) ---------------------
def test_roster_wids_and_routes_verbatim():
    public = roster_public()
    assert public[0] == {
        "name": "ORCHESTRATOR",
        "wid": "adidlabs/orchestrator-9f21",
        "route": "NOVA-PRO",
        "status": "standby",
    }
    # Exactly one nova-pro (orchestrator); the rest haiku-4.5.
    nova = [a for a in public if a["route"] == "NOVA-PRO"]
    haiku = [a for a in public if a["route"] == "HAIKU-4.5"]
    assert len(nova) == 1 and len(haiku) == 7
    assert len(ROSTER) == 8


def test_roster_order_is_contractual():
    names = [a["name"] for a in roster_public()]
    assert names == [
        "ORCHESTRATOR",
        "WEATHER",
        "SHOES",
        "PANTS",
        "TSHIRT",
        "JUMPER",
        "JACKET",
        "ACCESSORY",
    ]

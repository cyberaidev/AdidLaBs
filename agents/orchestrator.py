"""Orchestrator - LangGraph supervisor (route ``nova-pro``).

The orchestrator (``adidlabs/orchestrator-9f21``) drives one styling turn:

    weather_read  ->  route  ->  fan_out (A2A to specialists)  ->  compose

Graph nodes:
    * ``weather_read`` - normalize the 3-day forecast into structured conditions
      (delegated to :class:`~agents.weather_agent.WeatherAgent`).
    * ``route`` - decide which category specialists to consult. This is the
      **contract-bearing** step and is deterministic so it is testable with a
      mocked LLM: **rain => jacket + accessory**, **sun => tshirt + shoes**
      (plus sensible cold/mild defaults). An LLM may *widen* the set but can
      never drop a mandated category.
    * ``fan_out`` - send an A2A ``style_pick`` task to each chosen specialist
      (in-process; see agents/README.md for the cost tradeoff) and collect
      :class:`~agents.common.a2a.TaskResult` replies.
    * ``compose`` - merge picks into one stylist reply with citations. Uses the
      ``nova-pro`` route when an LLM is present; otherwise a deterministic
      template so the graph runs offline.

If LangGraph is unavailable at import time the module falls back to an
equivalent hand-rolled sequential runner exposing the same ``run`` API and a
``compile()`` method, so ``entrypoint`` and the tests behave identically.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .common.a2a import STATUS_OK, make_task
from .common.llm import LLMClient
from .common.roster import get_identity
from .common.tools import ToolClient, default_tool_client
from .shopping_agents import ShoppingAgent, build_shopping_agents
from .weather_agent import WeatherAgent

# --- Routing contract ------------------------------------------------------
# Weather condition -> ordered list of category specialists the orchestrator
# MUST consult. These pairs are the hard contract exercised by the unit tests.
ROUTING_RULES: dict[str, list[str]] = {
    "rain": ["jacket", "accessory"],
    "sun": ["tshirt", "shoes"],
    "cold": ["jumper", "jacket"],
    "mild": ["tshirt", "pants"],
}


def route_for_conditions(dominant: str) -> list[str]:
    """Return the mandated specialist list for a dominant condition.

    Unknown conditions fall back to the ``mild`` rule. The returned list is a
    fresh copy so callers may extend it safely.
    """
    return list(ROUTING_RULES.get(dominant, ROUTING_RULES["mild"]))


class OrchestratorState(TypedDict, total=False):
    """State passed between graph nodes."""

    user_message: str
    user_id: str
    forecast: dict[str, Any]
    conditions: dict[str, Any]
    routed: list[str]
    results: list[dict[str, Any]]
    reply: str
    picks: list[dict[str, Any]]
    citations: list[dict[str, Any]]


class Orchestrator:
    """Supervisor that compiles and runs the styling graph."""

    def __init__(
        self,
        tools: ToolClient | None = None,
        llm: LLMClient | None = None,
        *,
        specialists: dict[str, ShoppingAgent] | None = None,
        weather: WeatherAgent | None = None,
    ) -> None:
        self.identity = get_identity("orchestrator")
        self.tools = tools or default_tool_client()
        self.llm = llm
        self.weather = weather or WeatherAgent(llm=llm)
        self.specialists = specialists or build_shopping_agents(self.tools, llm)
        self._graph = self._build_graph()

    # -- graph nodes ---------------------------------------------------------
    def _node_weather_read(self, state: OrchestratorState) -> OrchestratorState:
        conditions = self.weather.read(forecast=state.get("forecast"))
        return {"conditions": conditions.to_dict()}

    def _node_route(self, state: OrchestratorState) -> OrchestratorState:
        dominant = state.get("conditions", {}).get("dominant", "mild")
        routed = route_for_conditions(dominant)
        routed = self._maybe_widen(state.get("user_message", ""), dominant, routed)
        return {"routed": routed}

    def _node_fan_out(self, state: OrchestratorState) -> OrchestratorState:
        conditions = state.get("conditions", {})
        user_message = state.get("user_message", "")
        results: list[dict[str, Any]] = []
        # In-process A2A fan-out: direct handler calls, one envelope each.
        for category in state.get("routed", []):
            agent = self.specialists.get(category)
            if agent is None:
                continue
            envelope = make_task(
                sender=self.identity.wid,
                recipient=agent.identity.wid,
                payload={"conditions": conditions, "user_message": user_message},
            )
            results.append(agent.handle(envelope).to_dict())
        return {"results": results}

    def _node_compose(self, state: OrchestratorState) -> OrchestratorState:
        results = state.get("results", [])
        conditions = state.get("conditions", {})
        picks: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        for res in results:
            if res.get("status") != STATUS_OK:
                continue
            picks.extend(res.get("picks", []))
            citations.extend(res.get("citations", []))
        reply = self._compose_reply(conditions, results)
        return {"picks": picks, "citations": citations, "reply": reply}

    # -- composition helpers -------------------------------------------------
    def _maybe_widen(self, user_message: str, dominant: str, routed: list[str]) -> list[str]:
        """Optionally add categories the user explicitly asks for.

        The mandated categories are always kept; the LLM/heuristic may only
        widen the set, never shrink it, so the routing contract holds.
        """
        widened = list(routed)
        text = (user_message or "").lower()
        for category in ("shoes", "pants", "tshirt", "jumper", "jacket", "accessory"):
            if category in text and category not in widened:
                widened.append(category)
        return widened

    def _compose_reply(self, conditions: dict[str, Any], results: list[dict[str, Any]]) -> str:
        summary = conditions.get("summary", "")
        lines = []
        for res in results:
            if res.get("status") != STATUS_OK or not res.get("picks"):
                continue
            wid = res.get("agent", "")
            titles = ", ".join(
                p.get("title", p.get("item_id", "item")) for p in res.get("picks", [])
            )
            lines.append(f"- {wid}: {titles} — {res.get('rationale','')}".rstrip())
        body = "\n".join(lines) if lines else "No picks matched this forecast."

        if self.llm is None:
            return f"{summary}\nHere are your weather-matched picks:\n{body}".strip()
        try:
            content = self.llm.chat(
                self.identity.route,
                [
                    {
                        "role": "system",
                        "content": "You are the AdidLaBs stylist orchestrator. "
                        "Weave the specialist picks into one warm, concise reply "
                        "(<=90 words). Keep the item names. No markdown headers.",
                    },
                    {
                        "role": "user",
                        "content": f"Forecast: {summary}\nSpecialist picks:\n{body}",
                    },
                ],
                temperature=0.4,
                max_tokens=220,
            ).strip()
            return content or f"{summary}\n{body}".strip()
        except Exception:  # noqa: BLE001 - deterministic fallback
            return f"{summary}\nHere are your weather-matched picks:\n{body}".strip()

    # -- graph wiring --------------------------------------------------------
    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:  # noqa: BLE001 - LangGraph optional; fall back
            return _SequentialGraph(self)

        graph = StateGraph(OrchestratorState)
        graph.add_node("weather_read", self._node_weather_read)
        graph.add_node("route", self._node_route)
        graph.add_node("fan_out", self._node_fan_out)
        graph.add_node("compose", self._node_compose)
        graph.add_edge(START, "weather_read")
        graph.add_edge("weather_read", "route")
        graph.add_edge("route", "fan_out")
        graph.add_edge("fan_out", "compose")
        graph.add_edge("compose", END)
        return graph.compile()

    def compile(self) -> Any:
        """Return the compiled graph (or the sequential fallback)."""
        return self._graph

    def run(
        self,
        user_message: str,
        *,
        forecast: dict[str, Any] | None = None,
        user_id: str = "demo-user",
    ) -> dict[str, Any]:
        """Run one styling turn end to end and return the final state.

        Args:
            user_message: The shopper's message.
            forecast: Raw Open-Meteo 3-day payload (or ``None`` for a mild default).
            user_id: Authenticated user id (JWT ``sub`` in production).

        Returns:
            Final state dict with ``reply``, ``picks``, ``citations``,
            ``routed``, and ``conditions``.
        """
        initial: OrchestratorState = {
            "user_message": user_message,
            "user_id": user_id,
            "forecast": forecast or {},
        }
        return dict(self._graph.invoke(initial))


class _SequentialGraph:
    """Fallback runner with the same ``invoke`` API as a compiled LangGraph.

    Used only when LangGraph is not importable; runs the four nodes in order and
    threads state so behaviour (and the routing contract) is identical.
    """

    def __init__(self, orch: "Orchestrator") -> None:
        self._orch = orch

    def invoke(self, state: OrchestratorState) -> OrchestratorState:
        merged: OrchestratorState = dict(state)  # type: ignore[assignment]
        for node in (
            self._orch._node_weather_read,
            self._orch._node_route,
            self._orch._node_fan_out,
            self._orch._node_compose,
        ):
            merged.update(node(merged))
        return merged


def build_orchestrator(
    tools: ToolClient | None = None, llm: LLMClient | None = None
) -> Orchestrator:
    """Factory used by the entrypoint and tests."""
    return Orchestrator(tools=tools, llm=llm)

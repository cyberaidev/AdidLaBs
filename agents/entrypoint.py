"""Bedrock AgentCore runtime entrypoint.

One AgentCore runtime hosts the whole LangGraph mesh (orchestrator + weather +
six specialists). The ``api-handler`` Lambda reaches it with
``InvokeAgentRuntime`` (env ``AGENTCORE_AGENT_ARN``) for ``POST /api/chat``.

The AgentCore runtime SDK invokes the ``@app.entrypoint`` callable with the
request payload. Our payload contract mirrors ``POST /api/chat``:

    {
      "message":  "<user text>",              # required
      "user_id":  "<jwt sub>",                 # optional (defaults to demo-user)
      "forecast": { ...open-meteo daily... }   # optional (mild default if absent)
    }

Response:

    {
      "reply":      "<stylist text>",
      "picks":      [ ...catalog items... ],
      "citations":  [ ... ],
      "routed":     [ "<category>", ... ],
      "conditions": { ...structured weather... },
      "agent":      "adidlabs/orchestrator-9f21"
    }

The orchestrator/tools/LLM are built once at module import (warm-container
reuse). If the ``bedrock-agentcore`` SDK is not installed (local dev / CI) we
export a tiny stand-in ``app`` with the same ``entrypoint`` decorator and a
``run`` shim so the file always imports and the graph can be exercised.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from typing import Any, Callable

from .common.llm import LLMClient
from .common.tools import default_tool_client
from .orchestrator import Orchestrator, build_orchestrator


def _make_orchestrator() -> Orchestrator:
    """Construct the orchestrator with the env-selected tool client + LLM."""
    tools = default_tool_client()
    llm = LLMClient()  # reads LITELLM_URL; agents degrade gracefully if unset
    return build_orchestrator(tools=tools, llm=llm)


# Built once per container; reused across warm invocations.
ORCHESTRATOR = _make_orchestrator()


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Core request handler: run one styling turn and shape the response.

    Kept SDK-agnostic so it is unit-testable and reused by both the real
    AgentCore ``entrypoint`` and the local stand-in.
    """
    payload = payload or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return {
            "reply": "Ask the stylist for a weather-matched outfit.",
            "picks": [],
            "citations": [],
            "routed": [],
            "conditions": {},
            "agent": ORCHESTRATOR.identity.wid,
        }
    forecast = payload.get("forecast") or {}
    user_id = str(payload.get("user_id") or "demo-user")
    state = ORCHESTRATOR.run(message, forecast=forecast, user_id=user_id)
    return {
        "reply": state.get("reply", ""),
        "picks": state.get("picks", []),
        "citations": state.get("citations", []),
        "routed": state.get("routed", []),
        "conditions": state.get("conditions", {}),
        "agent": ORCHESTRATOR.identity.wid,
    }


def _build_app() -> Any:
    """Return a BedrockAgentCoreApp, or a local stand-in if the SDK is absent."""
    try:
        from bedrock_agentcore.runtime import BedrockAgentCoreApp
    except Exception:  # noqa: BLE001 - SDK optional in local/CI
        return _LocalApp()

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload: dict[str, Any]) -> dict[str, Any]:  # noqa: D401
        """AgentCore entrypoint - one stylist turn."""
        return handle(payload)

    return app


class _LocalApp:
    """Stand-in for BedrockAgentCoreApp for local dev / CI.

    Provides a compatible ``entrypoint`` decorator and a ``run`` shim so
    ``python -m agents.entrypoint``-style smoke checks work without the SDK.
    """

    def __init__(self) -> None:
        self._entry: Callable[[dict[str, Any]], dict[str, Any]] = handle

    def entrypoint(self, fn: Callable[[dict[str, Any]], dict[str, Any]]):
        self._entry = fn
        return fn

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._entry(payload)

    def run(self) -> None:  # pragma: no cover - convenience only
        import json
        import sys

        raw = sys.stdin.read() or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw.strip()}
        print(json.dumps(self._entry(payload), ensure_ascii=False, indent=2))


# The object the AgentCore runtime imports and serves.
app = _build_app()


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    app.run()

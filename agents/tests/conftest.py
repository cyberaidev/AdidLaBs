"""Pytest fixtures + a mocked LLM client (no live Bedrock in CI).

The :class:`MockLLMClient` records every call and returns canned text/JSON, so
the whole mesh runs with zero network and zero model spend. It is a structural
stand-in for :class:`agents.common.llm.LLMClient` - same ``chat`` / ``chat_json``
signatures - and asserts that only the two allowed routes are ever used.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Make the repo root importable as `agents...` regardless of pytest's rootdir.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.common.llm import ALLOWED_ROUTES  # noqa: E402


class MockLLMClient:
    """Deterministic stand-in for the LiteLLM-backed client.

    Records calls in ``self.calls`` as ``(route, messages)`` tuples and returns
    a fixed short string (or ``{}`` for JSON). Raises if a disallowed route is
    used, guaranteeing tests never depend on a raw Bedrock model id.
    """

    def __init__(self, reply: str = "Styled for the forecast.") -> None:
        self.reply = reply
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def chat(self, route: str, messages: list[dict[str, str]], **_: Any) -> str:
        assert route in ALLOWED_ROUTES, f"disallowed route {route!r}"
        self.calls.append((route, messages))
        return self.reply

    def chat_json(self, route: str, messages: list[dict[str, str]], **_: Any) -> Any:
        assert route in ALLOWED_ROUTES, f"disallowed route {route!r}"
        self.calls.append((route, messages))
        return {}

    def routes_used(self) -> set[str]:
        return {route for route, _ in self.calls}


@pytest.fixture(autouse=True)
def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force DEMO_MODE and clear LITELLM_URL so nothing tries to hit a gateway."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.delenv("LITELLM_URL", raising=False)


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()


def _daily(codes: list[int], highs: list[float], lows: list[float]) -> dict[str, Any]:
    times = ["2026-07-18", "2026-07-19", "2026-07-20"][: len(codes)]
    return {
        "daily": {
            "time": times,
            "weathercode": codes,
            "temperature_2m_max": highs,
            "temperature_2m_min": lows,
        }
    }


@pytest.fixture
def rain_forecast() -> dict[str, Any]:
    """A clearly wet 3-day window (WMO 61/63/80 = rain)."""
    return _daily([61, 63, 80], [14.0, 15.0, 13.0], [9.0, 10.0, 8.0])


@pytest.fixture
def sun_forecast() -> dict[str, Any]:
    """A warm, clear 3-day window (WMO 0/1 = clear/mainly clear)."""
    return _daily([0, 1, 0], [27.0, 29.0, 28.0], [17.0, 18.0, 16.0])

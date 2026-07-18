"""Agent roster - workload identities and model-route assignments.

This is the single source of truth inside the agents module for:

    * each agent's AgentCore **workload identity id** (``wid``), and
    * which LiteLLM **route** it uses.

The frontend renders these wids verbatim (see docs/design.md section 5.10) and
``GET /api/agents`` serves the same roster, so the strings here MUST match the
contract exactly. Model routes are referenced by *name* only - never a raw
Bedrock model id (see common/llm.py).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from dataclasses import dataclass

from .llm import ROUTE_HAIKU, ROUTE_NOVA_PRO

# Category keys used across the mesh, MCP catalog filtering, and tests.
CATEGORIES = ("shoes", "pants", "tshirt", "jumper", "jacket", "accessory")


@dataclass(frozen=True)
class AgentIdentity:
    """Static identity + model assignment for one agent.

    Attributes:
        key: Short internal key (``"orchestrator"``, ``"weather"``, category...).
        name: Display name (uppercase) as shown by the frontend.
        wid: AgentCore workload identity id - rendered verbatim by the UI.
        route: LiteLLM route name this agent calls (``nova-pro``/``haiku-4.5``).
        category: Catalog category for shopping agents; ``None`` otherwise.
    """

    key: str
    name: str
    wid: str
    route: str
    category: str | None = None


# Order matters: orchestrator first, weather second, then the six categories.
ROSTER: tuple[AgentIdentity, ...] = (
    AgentIdentity("orchestrator", "ORCHESTRATOR", "adidlabs/orchestrator-9f21", ROUTE_NOVA_PRO),
    AgentIdentity("weather", "WEATHER", "adidlabs/weather-3b7c", ROUTE_HAIKU),
    AgentIdentity("shoes", "SHOES", "adidlabs/shoes-4e2a", ROUTE_HAIKU, "shoes"),
    AgentIdentity("pants", "PANTS", "adidlabs/pants-8c1d", ROUTE_HAIKU, "pants"),
    AgentIdentity("tshirt", "TSHIRT", "adidlabs/tshirt-2a9e", ROUTE_HAIKU, "tshirt"),
    AgentIdentity("jumper", "JUMPER", "adidlabs/jumper-6d3f", ROUTE_HAIKU, "jumper"),
    AgentIdentity("jacket", "JACKET", "adidlabs/jacket-1e8b", ROUTE_HAIKU, "jacket"),
    AgentIdentity("accessory", "ACCESSORY", "adidlabs/accessory-5c4a", ROUTE_HAIKU, "accessory"),
)

_BY_KEY = {a.key: a for a in ROSTER}
_BY_CATEGORY = {a.category: a for a in ROSTER if a.category is not None}


def get_identity(key: str) -> AgentIdentity:
    """Return the identity for an agent key. Raises ``KeyError`` if unknown."""
    return _BY_KEY[key]


def get_category_identity(category: str) -> AgentIdentity:
    """Return the specialist identity for a catalog category."""
    return _BY_CATEGORY[category]


def category_identities() -> tuple[AgentIdentity, ...]:
    """Return the six shopping-agent identities in roster order."""
    return tuple(a for a in ROSTER if a.category is not None)


def roster_public() -> list[dict[str, str]]:
    """Return the roster as the frontend / ``GET /api/agents`` shape.

    Status is a live value the API layer owns; the agents module reports the
    static ``standby`` default. Route chips are uppercased to match the UI.
    """
    return [
        {
            "name": a.name,
            "wid": a.wid,
            "route": a.route.upper(),
            "status": "standby",
        }
        for a in ROSTER
    ]

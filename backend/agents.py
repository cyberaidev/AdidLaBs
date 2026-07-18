"""GET /api/agents - agent roster + workload identities + status.

Returns the eight-agent roster exactly as specified in the contracts. The
frontend renders each ``wid`` and route chip verbatim (design Sec. 5.10), so
these strings are the source of truth and must never be invented.

Status model (design Sec. 5.9): agents are ``standby`` before login and flip to
``running`` after login as the chat fans out. The frontend drives the visual
transition; this endpoint reports a status derived from the ``authed`` query
flag so a page reload after login still shows ``running``.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

from typing import Any, Mapping

from common.http import error, get_method, get_query, preflight, respond

# Ordering is contractual: orchestrator, weather, then the six category agents.
ROSTER: list[dict[str, str]] = [
    {"name": "ORCHESTRATOR", "wid": "adidlabs/orchestrator-9f21", "route": "nova-pro"},
    {"name": "WEATHER", "wid": "adidlabs/weather-3b7c", "route": "haiku-4.5"},
    {"name": "SHOES", "wid": "adidlabs/shoes-4e2a", "route": "haiku-4.5"},
    {"name": "PANTS", "wid": "adidlabs/pants-8c1d", "route": "haiku-4.5"},
    {"name": "TSHIRT", "wid": "adidlabs/tshirt-2a9e", "route": "haiku-4.5"},
    {"name": "JUMPER", "wid": "adidlabs/jumper-6d3f", "route": "haiku-4.5"},
    {"name": "JACKET", "wid": "adidlabs/jacket-1e8b", "route": "haiku-4.5"},
    {"name": "ACCESSORY", "wid": "adidlabs/accessory-5c4a", "route": "haiku-4.5"},
]


def _is_truthy(value: str | None) -> bool:
    """Interpret a query flag (``authed=1``/``true``) as a boolean."""
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def build_roster(authed: bool) -> list[dict[str, str]]:
    """Return the roster with a status field applied.

    Post-auth every agent reports ``running``; pre-auth every agent reports
    ``standby``. A fresh copy is returned so the module constant is never
    mutated across invocations.
    """
    status = "running" if authed else "standby"
    return [{**agent, "status": status} for agent in ROSTER]


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/agents."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    authed = _is_truthy(get_query(event).get("authed"))
    return respond(
        200,
        {
            "region": "ap-southeast-2",
            "count": len(ROSTER),
            "agents": build_roster(authed),
        },
    )

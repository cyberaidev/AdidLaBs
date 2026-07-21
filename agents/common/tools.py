"""MCP tool client for the AgentCore Gateway tool surface.

Agents consume six MCP tools exposed by the AgentCore Gateway:

    get_catalog(category=None, limit=...)   -> list[item]      (DynamoDB catalog)
    get_deals(category=None, limit=...)      -> list[item]      (discounted items)
    bag_add(user_id, item_id, qty=1)         -> {"ok": True}    (DynamoDB bag)
    bag_get(user_id)                         -> list[bag_row]
    search_lab_knowledge(query, top_k=...)   -> list[passage]   (Bedrock KB retrieve)
    search_web(query, max_results=...)       -> list[web_hit]   (ddgs / Tavily)

At runtime, agents reach these over MCP through the Gateway. To keep the graph
loadable and the routing tests hermetic (no live Bedrock / DynamoDB / network),
this module provides a :class:`ToolClient` protocol plus an in-process
:class:`LocalToolClient` backed by ``data/synthetic_fallback.json`` (falling back
to a tiny built-in seed if that file is absent). The orchestrator/agents depend
only on the protocol, so the real MCP-backed client is a drop-in swap.

Env:
    DEMO_MODE - when truthy, agents default to :class:`LocalToolClient`.
    TAVILY_API_KEY - documented here for parity; the real search_web tool lives
        on the Gateway and uses ddgs by default, Tavily when this key is set.

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Relevance threshold below which KB passages are treated as a "miss" and the
# agent falls back to search_web. KB retrieve scores are ~cosine in [0, 1].
KB_RELEVANCE_FLOOR = 0.35


@runtime_checkable
class ToolClient(Protocol):
    """The MCP tool surface agents depend on (Gateway-backed in production)."""

    def get_catalog(self, category: str | None = None, limit: int = 24) -> list[dict[str, Any]]: ...

    def get_deals(self, category: str | None = None, limit: int = 24) -> list[dict[str, Any]]: ...

    def bag_add(self, user_id: str, item_id: str, qty: int = 1) -> dict[str, Any]: ...

    def bag_get(self, user_id: str) -> list[dict[str, Any]]: ...

    def search_lab_knowledge(self, query: str, top_k: int = 4) -> list[dict[str, Any]]: ...

    def search_web(self, query: str, max_results: int = 4) -> list[dict[str, Any]]: ...


# Minimal built-in seed so the module works even before data/ is generated.
_BUILTIN_SEED: list[dict[str, Any]] = [
    {"item_id": "shoes-0001", "category": "shoes", "title": "Trail Runner Low", "price": 89.0, "deal_pct": 0},
    {"item_id": "shoes-0002", "category": "shoes", "title": "All-Weather Sneaker", "price": 110.0, "deal_pct": 20},
    {"item_id": "pants-0001", "category": "pants", "title": "Tapered Track Pant", "price": 65.0, "deal_pct": 0},
    {"item_id": "tshirt-0001", "category": "tshirt", "title": "Breathable Training Tee", "price": 29.0, "deal_pct": 0},
    {"item_id": "tshirt-0002", "category": "tshirt", "title": "Cotton Everyday Tee", "price": 22.0, "deal_pct": 15},
    {"item_id": "jumper-0001", "category": "jumper", "title": "Midweight Crew Jumper", "price": 79.0, "deal_pct": 0},
    {"item_id": "jacket-0001", "category": "jacket", "title": "Packable Rain Jacket", "price": 129.0, "deal_pct": 25},
    {"item_id": "jacket-0002", "category": "jacket", "title": "Windbreaker Shell", "price": 99.0, "deal_pct": 0},
    {"item_id": "accessory-0001", "category": "accessory", "title": "Compact Umbrella", "price": 19.0, "deal_pct": 0},
    {"item_id": "accessory-0002", "category": "accessory", "title": "Water-Repellent Cap", "price": 24.0, "deal_pct": 10},
]

# Tiny KB seed mapping weather intent -> grounded style guidance passages.
# NOTE: keywords are WEATHER terms only (not clothing categories). The corpus is
# a weather-to-outfit guide keyed by conditions, so a query with no weather
# signal (e.g. "mild" + off-topic text) correctly misses and falls back to web.
_BUILTIN_KB: list[dict[str, Any]] = [
    {
        "text": "For rain and wind, a packable rain jacket keeps the outfit dry; "
        "pair it with a compact umbrella or a water-repellent cap.",
        "source": "weather-to-outfit-guide.md#rain",
        "keywords": ["rain", "wind", "wet", "shower", "drizzle", "storm"],
    },
    {
        "text": "On warm, sunny days choose a breathable t-shirt and a low-profile "
        "sneaker; light colours reflect heat and stay comfortable.",
        "source": "weather-to-outfit-guide.md#sun",
        "keywords": ["sun", "sunny", "warm", "hot", "clear"],
    },
    {
        "text": "For cold snaps, layer a midweight jumper under a shell and keep a "
        "warm accessory to hand.",
        "source": "weather-to-outfit-guide.md#cold",
        "keywords": ["cold", "cool", "snow", "chill", "frost"],
    },
]


def _load_seed_items() -> list[dict[str, Any]]:
    """Load catalog seed from data/synthetic_fallback.json, else the builtin seed."""
    # agents/common/tools.py -> repo root is two parents up from this file's dir.
    candidate = Path(__file__).resolve().parents[2] / "data" / "synthetic_fallback.json"
    if candidate.is_file():
        try:
            raw = json.loads(candidate.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return list(_BUILTIN_SEED)
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        norm: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            norm.append(
                {
                    "item_id": it.get("item_id") or it.get("id") or "",
                    "category": (it.get("category") or "").lower(),
                    "title": it.get("title") or it.get("name") or "Item",
                    "price": float(it.get("price", it.get("price_usd", it.get("price_eur", 0))) or 0),
                    "deal_pct": int(it.get("deal_pct", it.get("discount_pct", 0)) or 0),
                }
            )
        return norm or list(_BUILTIN_SEED)
    return list(_BUILTIN_SEED)


class LocalToolClient:
    """In-process implementation of the MCP tool surface for demo/CI.

    Reads the catalog seed once at construction. ``bag_*`` operates on an
    in-memory per-``user_id`` store. ``search_lab_knowledge`` scores a tiny
    keyword-weighted corpus so KB-miss fallback logic is exercisable offline.
    """

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self._items = list(items) if items is not None else _load_seed_items()
        self._bags: dict[str, dict[str, int]] = {}

    # -- structured (DynamoDB-backed in prod) --------------------------------
    def get_catalog(self, category: str | None = None, limit: int = 24) -> list[dict[str, Any]]:
        rows = self._items
        if category:
            rows = [i for i in rows if i.get("category") == category]
        return [dict(i) for i in rows[:limit]]

    def get_deals(self, category: str | None = None, limit: int = 24) -> list[dict[str, Any]]:
        rows = [i for i in self._items if int(i.get("deal_pct", 0)) > 0]
        if category:
            rows = [i for i in rows if i.get("category") == category]
        rows.sort(key=lambda i: int(i.get("deal_pct", 0)), reverse=True)
        return [dict(i) for i in rows[:limit]]

    def bag_add(self, user_id: str, item_id: str, qty: int = 1) -> dict[str, Any]:
        bag = self._bags.setdefault(user_id, {})
        bag[item_id] = bag.get(item_id, 0) + max(1, int(qty))
        return {"ok": True, "item_id": item_id, "qty": bag[item_id]}

    def bag_get(self, user_id: str) -> list[dict[str, Any]]:
        bag = self._bags.get(user_id, {})
        return [{"item_id": iid, "qty": qty} for iid, qty in bag.items()]

    # -- knowledge / web -----------------------------------------------------
    def search_lab_knowledge(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        q = (query or "").lower()
        scored: list[dict[str, Any]] = []
        for passage in _BUILTIN_KB:
            hits = sum(1 for kw in passage["keywords"] if kw in q)
            if hits == 0:
                continue
            score = min(1.0, KB_RELEVANCE_FLOOR + 0.2 * hits)
            scored.append(
                {"text": passage["text"], "source": passage["source"], "score": round(score, 3)}
            )
        scored.sort(key=lambda p: p["score"], reverse=True)
        return scored[:top_k]

    def search_web(self, query: str, max_results: int = 4) -> list[dict[str, Any]]:
        # Deterministic stub for offline/demo. The real Gateway tool uses
        # ddgs by default and Tavily when TAVILY_API_KEY is set.
        return [
            {
                "title": f"Style note for: {query}",
                "url": "https://example.invalid/style",
                "snippet": "General weather-appropriate styling guidance (demo web fallback).",
            }
        ][:max_results]


def default_tool_client() -> ToolClient:
    """Return the tool client to use given the environment.

    In production the AgentCore Gateway MCP client would be constructed here.
    For DEMO_MODE / CI (and whenever no gateway is wired), return the in-process
    :class:`LocalToolClient` so the graph is fully runnable.
    """
    # A real deployment swaps this branch for a Gateway-backed MCP client.
    _ = os.environ.get("DEMO_MODE")  # documented switch; local client either way here
    return LocalToolClient()


def kb_is_useful(passages: list[dict[str, Any]]) -> bool:
    """True if any KB passage clears :data:`KB_RELEVANCE_FLOOR`."""
    return any(float(p.get("score", 0.0)) >= KB_RELEVANCE_FLOOR for p in passages)

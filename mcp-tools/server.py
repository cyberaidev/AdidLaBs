"""AdidLaBs MCP tools server.

Concept demo - no affiliation with adidas AG. All products fictional.

Exposes the six LLM-free tools consumed by the AgentCore agent mesh through an
AgentCore Gateway (MCP surface):

    get_catalog          - structured lookups over the adidlabs-catalog table
    get_deals            - discounted items from adidlabs-catalog
    bag_add              - add an item to a user's adidlabs-bag
    bag_get              - read a user's current bag
    search_lab_knowledge - semantic RAG over the Bedrock Knowledge Base (KB_ID)
    search_web           - KB-miss fallback: ddgs (free) by default, Tavily when
                           TAVILY_API_KEY is set; results are marked web-sourced

Design rules (see docs/architecture.md):
  * Structured facts (price, stock, deals, bag) stay as plain DynamoDB tools.
  * Only narrative knowledge goes through RAG (search_lab_knowledge).
  * search_lab_knowledge degrades gracefully to search_web when the KB is
    unavailable, and every tool returns relevance/source metadata so the
    orchestrator can gate KB-vs-web.

All boto3 clients and network calls live in tiny module-level helpers so unit
tests can stub them without touching real DynamoDB, Bedrock, ddgs, or Tavily.

Region: ap-southeast-2 (Sydney). Every resource is created there.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Configuration (exact env var names per the contract).
# --------------------------------------------------------------------------- #

REGION = "ap-southeast-2"

# Relevance gate: search_lab_knowledge tells the orchestrator whether the top KB
# hit is strong enough to ground on. Below this, the orchestrator should call
# search_web. Kept here (not in the LLM prompt) so gating is deterministic.
KB_RELEVANCE_THRESHOLD = 0.40

# Default number of results.
DEFAULT_TOP_K = 5


def _env(name: str, default: str = "") -> str:
    """Read an env var at call time (never cached), so tests can set/clear it."""
    return os.environ.get(name, default)


# --------------------------------------------------------------------------- #
# boto3 client factories - one per service. Isolated so tests monkeypatch them.
# Clients are created per call; boto3 caches sessions internally and these tools
# run inside request-scoped Lambdas, so there is no always-on connection.
# --------------------------------------------------------------------------- #

def _dynamodb_resource():  # pragma: no cover - thin boto3 wrapper, stubbed in tests
    import boto3

    return boto3.resource("dynamodb", region_name=REGION)


def _bedrock_agent_runtime_client():  # pragma: no cover - stubbed in tests
    import boto3

    return boto3.client("bedrock-agent-runtime", region_name=REGION)


# --------------------------------------------------------------------------- #
# Serialization helpers - DynamoDB returns Decimal; JSON/MCP wants plain numbers.
# --------------------------------------------------------------------------- #

def _normalize(value: Any) -> Any:
    """Recursively convert DynamoDB Decimals into int/float for clean output."""
    if isinstance(value, Decimal):
        # Preserve integers as int, everything else as float.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def _to_decimal(value: Any) -> Any:
    """Convert incoming numbers to Decimal for DynamoDB put_item."""
    if isinstance(value, float):
        # str() avoids binary float noise that DynamoDB rejects.
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_decimal(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# Tool implementations (pure functions - the MCP tool wrappers just call these).
# Keeping the logic in `_impl` functions makes them directly unit-testable and
# lets register_gateway.py enumerate them without spinning up a transport.
# --------------------------------------------------------------------------- #

def get_catalog_impl(
    category: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = 24,
) -> Dict[str, Any]:
    """Return catalog items from the adidlabs-catalog DynamoDB table.

    Args:
        category: optional category filter (shoes, pants, tshirt, jumper,
            jacket, accessory). Case-insensitive.
        item_id: optional exact item_id lookup (returns 0 or 1 item).
        limit: max items to return when scanning/filtering (default 24).

    Returns a structured payload; this is a plain data lookup, NOT RAG.
    """
    table_name = _env("CATALOG_TABLE", "adidlabs-catalog")
    table = _dynamodb_resource().Table(table_name)

    if item_id:
        resp = table.get_item(Key={"item_id": item_id})
        item = resp.get("Item")
        items = [_normalize(item)] if item else []
        return {"source": "catalog", "count": len(items), "items": items}

    if category:
        from boto3.dynamodb.conditions import Attr

        resp = table.scan(
            FilterExpression=Attr("category").eq(category.lower()),
            Limit=max(1, int(limit)),
        )
    else:
        resp = table.scan(Limit=max(1, int(limit)))

    items = [_normalize(i) for i in resp.get("Items", [])]
    return {"source": "catalog", "count": len(items), "items": items}


def get_deals_impl(
    category: Optional[str] = None,
    limit: int = 24,
) -> Dict[str, Any]:
    """Return discounted items (deal_pct > 0) from adidlabs-catalog.

    Args:
        category: optional category filter.
        limit: max deal items to return.

    Plain structured lookup - deterministic, no LLM, no RAG.
    """
    from boto3.dynamodb.conditions import Attr

    table_name = _env("CATALOG_TABLE", "adidlabs-catalog")
    table = _dynamodb_resource().Table(table_name)

    condition = Attr("deal_pct").gt(0)
    if category:
        condition = condition & Attr("category").eq(category.lower())

    want = max(1, int(limit))

    # DynamoDB applies `Limit` to items *scanned*, not items *matched* by the
    # FilterExpression: a single scan page can therefore under-return deals when
    # the matching rows are sparse in a large table. To make `limit` mean
    # "matched deals returned" we page through the scan (following
    # LastEvaluatedKey) and accumulate matches until we have enough. The mock
    # catalog is small so this is one page in practice, but it stays correct if
    # the table ever grows.
    items: List[Dict[str, Any]] = []
    scan_kwargs: Dict[str, Any] = {"FilterExpression": condition}
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(_normalize(i) for i in resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if len(items) >= want or not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    # Highest discount first so the stylist surfaces the best deals, then cap.
    items.sort(key=lambda i: i.get("deal_pct", 0), reverse=True)
    items = items[:want]
    return {"source": "deals", "count": len(items), "items": items}


def bag_add_impl(
    user_id: str,
    item_id: str,
    qty: int = 1,
    title: Optional[str] = None,
    price: Optional[float] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Add (or upsert) an item into a user's bag in adidlabs-bag.

    The table is keyed pk=user_id, sk=item_id. The user_id is always supplied
    by the orchestrator from the JWT `sub` claim - never from untrusted input.

    Args:
        user_id: authenticated user id (JWT sub).
        item_id: catalog item id.
        qty: quantity to add (default 1).
        title/price/category: optional denormalized fields for fast bag render.

    Returns the written row.
    """
    if not user_id or not item_id:
        return {"ok": False, "error": "user_id and item_id are required"}

    # Coerce qty to a sane positive integer. Anything non-positive (0, a
    # negative like -3, or an unparseable value) collapses to 1 so a bad qty can
    # never persist and poison bag_get's price*qty subtotal math.
    try:
        qty_int = int(qty)
    except (TypeError, ValueError):
        qty_int = 1
    if qty_int < 1:
        qty_int = 1

    table_name = _env("BAG_TABLE", "adidlabs-bag")
    table = _dynamodb_resource().Table(table_name)

    row: Dict[str, Any] = {
        "user_id": user_id,
        "item_id": item_id,
        "qty": qty_int,
    }
    if title is not None:
        row["title"] = title
    if price is not None:
        row["price"] = price
    if category is not None:
        row["category"] = category.lower()

    table.put_item(Item=_to_decimal(row))
    # We echo the just-written `row` (already plain int/float) rather than a
    # read-back of the persisted item. Values are identical to what was stored,
    # so _normalize is a no-op here; we run it for shape-consistency with the
    # other tools that return DynamoDB Decimals.
    return {"ok": True, "action": "bag_add", "item": _normalize(row)}


def bag_get_impl(user_id: str) -> Dict[str, Any]:
    """Return the current bag for a user from adidlabs-bag.

    Args:
        user_id: authenticated user id (JWT sub).

    Returns all rows under the pk=user_id partition plus a subtotal.
    """
    if not user_id:
        return {"ok": False, "error": "user_id is required", "items": []}

    from boto3.dynamodb.conditions import Key

    table_name = _env("BAG_TABLE", "adidlabs-bag")
    table = _dynamodb_resource().Table(table_name)

    resp = table.query(KeyConditionExpression=Key("user_id").eq(user_id))
    items = [_normalize(i) for i in resp.get("Items", [])]

    subtotal = 0.0
    for i in items:
        subtotal += float(i.get("price", 0) or 0) * int(i.get("qty", 1) or 1)

    return {
        "ok": True,
        "source": "bag",
        "user_id": user_id,
        "count": len(items),
        "subtotal": round(subtotal, 2),
        "currency": "EUR",
        "items": items,
    }


def search_lab_knowledge_impl(
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    """Semantic RAG over the Bedrock Knowledge Base (KB_ID).

    Calls bedrock-agent-runtime `retrieve` against KB_ID and returns the top
    chunks with their relevance scores. The orchestrator uses `top_score` and
    `relevant` to decide whether to ground on the KB or fall back to
    search_web.

    Graceful degradation: if KB_ID is unset or the retrieve call raises (KB
    unavailable / S3 Vectors preview hiccup), this transparently calls
    search_web and returns those results marked source="web" with
    degraded=True, so agents keep working with no signature change.

    Args:
        query: natural-language knowledge query.
        top_k: number of chunks to retrieve.
    """
    kb_id = _env("KB_ID")
    if not kb_id:
        return _degrade_to_web(query, top_k, reason="KB_ID not configured")

    try:
        client = _bedrock_agent_runtime_client()
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max(1, int(top_k))}
            },
        )
    except Exception as exc:  # noqa: BLE001 - any KB failure degrades to web
        return _degrade_to_web(query, top_k, reason=f"KB retrieve failed: {exc}")

    results: List[Dict[str, Any]] = []
    for r in resp.get("retrievalResults", []):
        content = r.get("content", {}) or {}
        location = r.get("location", {}) or {}
        s3_loc = location.get("s3Location", {}) or {}
        results.append(
            {
                "text": content.get("text", ""),
                "score": float(r.get("score", 0.0) or 0.0),
                "source_uri": s3_loc.get("uri", ""),
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    top_score = results[0]["score"] if results else 0.0
    relevant = bool(results) and top_score >= KB_RELEVANCE_THRESHOLD

    return {
        "source": "kb",
        "degraded": False,
        "query": query,
        "count": len(results),
        "top_score": top_score,
        "threshold": KB_RELEVANCE_THRESHOLD,
        # The orchestrator gates on this: True => ground on KB, False => web.
        "relevant": relevant,
        "results": results,
    }


def search_web_impl(
    query: str,
    max_results: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    """KB-miss fallback web search. Results are always marked web-sourced.

    Uses Tavily (REST) when TAVILY_API_KEY is set, otherwise ddgs / DuckDuckGo
    (free, keyless). The orchestrator only calls this when KB relevance is low.

    Args:
        query: search query.
        max_results: number of results to return.

    Every returned item carries source="web" and a provider label so callers
    (and the UI) can clearly mark results as web-sourced, not brand knowledge.
    """
    tavily_key = _env("TAVILY_API_KEY")
    if tavily_key:
        return _search_web_tavily(query, max_results, tavily_key)
    return _search_web_ddgs(query, max_results)


# --------------------------------------------------------------------------- #
# Web-search backends (isolated for stubbing).
# --------------------------------------------------------------------------- #

def _search_web_ddgs(query: str, max_results: int) -> Dict[str, Any]:
    """Free DuckDuckGo search via the `ddgs` package."""
    try:
        from ddgs import DDGS
    except Exception as exc:  # noqa: BLE001 - import guarded so tool never crashes
        return {
            "source": "web",
            "provider": "ddgs",
            "web_sourced": True,
            "query": query,
            "count": 0,
            "results": [],
            "error": f"ddgs unavailable: {exc}",
        }

    results: List[Dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max(1, int(max_results))):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", "") or r.get("url", ""),
                        "snippet": r.get("body", "") or r.get("snippet", ""),
                        "web_sourced": True,
                    }
                )
    except Exception as exc:  # noqa: BLE001 - network errors degrade to empty
        return {
            "source": "web",
            "provider": "ddgs",
            "web_sourced": True,
            "query": query,
            "count": 0,
            "results": [],
            "error": f"ddgs search failed: {exc}",
        }

    return {
        "source": "web",
        "provider": "ddgs",
        "web_sourced": True,
        "query": query,
        "count": len(results),
        "results": results,
    }


def _search_web_tavily(query: str, max_results: int, api_key: str) -> Dict[str, Any]:
    """Tavily REST search - used only when TAVILY_API_KEY is set."""
    import requests

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max(1, int(max_results)),
                "search_depth": "basic",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - fall back to ddgs on any Tavily error
        ddgs_result = _search_web_ddgs(query, max_results)
        ddgs_result["note"] = f"tavily failed, used ddgs: {exc}"
        return ddgs_result

    results: List[Dict[str, Any]] = []
    for r in data.get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "score": float(r.get("score", 0.0) or 0.0),
                "web_sourced": True,
            }
        )

    return {
        "source": "web",
        "provider": "tavily",
        "web_sourced": True,
        "query": query,
        "count": len(results),
        "results": results,
    }


def _degrade_to_web(query: str, top_k: int, reason: str) -> Dict[str, Any]:
    """Wrap search_web output in the search_lab_knowledge envelope shape.

    Keeps the KB tool's return contract stable (same keys) while flagging that
    the KB was bypassed. `relevant` is False so the orchestrator treats these as
    web-sourced, not authoritative brand knowledge.
    """
    web = search_web_impl(query, max_results=top_k)
    results = [
        {
            "text": r.get("snippet", ""),
            "score": r.get("score", 0.0),
            "source_uri": r.get("url", ""),
        }
        for r in web.get("results", [])
    ]
    return {
        "source": "web",
        "degraded": True,
        "degrade_reason": reason,
        "provider": web.get("provider"),
        "query": query,
        "count": len(results),
        "top_score": 0.0,
        "threshold": KB_RELEVANCE_THRESHOLD,
        "relevant": False,
        "results": results,
    }


# --------------------------------------------------------------------------- #
# MCP server + tool registration.
# --------------------------------------------------------------------------- #

mcp = FastMCP("adidlabs-tools")


@mcp.tool()
def get_catalog(
    category: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = 24,
) -> Dict[str, Any]:
    """Look up AdidLaBs catalog items (price/stock/category) by category or id."""
    return get_catalog_impl(category=category, item_id=item_id, limit=limit)


@mcp.tool()
def get_deals(category: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
    """List discounted AdidLaBs catalog items, best discount first."""
    return get_deals_impl(category=category, limit=limit)


@mcp.tool()
def bag_add(
    user_id: str,
    item_id: str,
    qty: int = 1,
    title: Optional[str] = None,
    price: Optional[float] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Add an item to the authenticated user's shopping bag."""
    return bag_add_impl(
        user_id=user_id,
        item_id=item_id,
        qty=qty,
        title=title,
        price=price,
        category=category,
    )


@mcp.tool()
def bag_get(user_id: str) -> Dict[str, Any]:
    """Read the authenticated user's current shopping bag and subtotal."""
    return bag_get_impl(user_id=user_id)


@mcp.tool()
def search_lab_knowledge(query: str, top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """Semantic RAG over the AdidLaBs Knowledge Base; degrades to web on miss."""
    return search_lab_knowledge_impl(query=query, top_k=top_k)


@mcp.tool()
def search_web(query: str, max_results: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """Web-search fallback (ddgs by default, Tavily when keyed). Web-sourced."""
    return search_web_impl(query=query, max_results=max_results)


# The canonical tool registry - consumed by register_gateway.py and tests so the
# gateway targets and the MCP surface can never drift out of sync.
TOOL_SPECS: List[Dict[str, str]] = [
    {
        "name": "get_catalog",
        "description": "Structured price/stock/category lookups over adidlabs-catalog (DynamoDB). Not RAG.",
        "backend": "dynamodb:adidlabs-catalog",
    },
    {
        "name": "get_deals",
        "description": "Discounted catalog items (deal_pct > 0) from adidlabs-catalog, best deal first.",
        "backend": "dynamodb:adidlabs-catalog",
    },
    {
        "name": "bag_add",
        "description": "Add/upsert an item into a user's bag (adidlabs-bag, pk user_id, sk item_id).",
        "backend": "dynamodb:adidlabs-bag",
    },
    {
        "name": "bag_get",
        "description": "Read a user's current bag and subtotal from adidlabs-bag.",
        "backend": "dynamodb:adidlabs-bag",
    },
    {
        "name": "search_lab_knowledge",
        "description": "Semantic RAG over the Bedrock Knowledge Base (KB_ID); returns chunks + scores; degrades to web.",
        "backend": "bedrock-agent-runtime:retrieve",
    },
    {
        "name": "search_web",
        "description": "KB-miss web fallback: ddgs (free) or Tavily when keyed; results marked web-sourced.",
        "backend": "ddgs|tavily",
    },
]


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    # AgentCore Gateway hosts this over the MCP stdio transport.
    mcp.run()

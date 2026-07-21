"""GET /api/catalog - full category listings for manual browsing.

The product rail shows AI-matched picks; this route powers the per-category
"browse all" drawers so shoppers can search the whole catalog manually.
Backed by a scan of ``adidlabs-catalog`` (200 demo items - a scan is fine and
stays inside the free tier). Rows are mapped to the SPA's display shape.

Query params:
  * ``category``  one of shoes|pants|tshirt|jumper|jacket|accessory (optional)
  * ``limit``     max items (default 60, max 200)

Public like /api/agents: fictional demo catalog, no user data. Prices in USD.

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Mapping

import boto3
from boto3.dynamodb.conditions import Attr

from common.http import error, get_method, get_query, preflight, respond

_DEFAULT_LIMIT = 60
_MAX_LIMIT = 200
_CATEGORIES = {"shoes", "pants", "tshirt", "jumper", "jacket", "accessory"}


def _table():
    name = os.environ.get("CATALOG_TABLE", "adidlabs-catalog")
    ddb = boto3.resource(
        "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")
    )
    return ddb.Table(name)


def _num(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _display(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map a catalog row to the SPA's item shape (price + optional deal)."""
    original = _num(row.get("original_price")) or _num(row.get("price"))
    current = _num(row.get("price")) or original
    on_deal = current < original
    return {
        "item_id": str(row.get("item_id", "")),
        "title": str(row.get("name") or row.get("item_id") or "Item"),
        "category": str(row.get("category", "")).upper(),
        "price": round(original if on_deal else current, 2),
        "deal_price": round(current, 2) if on_deal else None,
        "colour": row.get("base_colour"),
        "article_type": row.get("article_type"),
        "gender": row.get("gender"),
        "season": row.get("season"),
    }


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for GET /api/catalog."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "GET":
        return error(405, "method not allowed")

    query = get_query(event)
    category = (query.get("category") or "").strip().lower()
    if category and category not in _CATEGORIES:
        return error(400, f"unknown category; expected one of {sorted(_CATEGORIES)}")
    try:
        limit = min(int(query.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)
    except ValueError:
        return error(400, "limit must be an integer")
    if limit < 1:
        return error(400, "limit must be positive")

    table = _table()
    scan_kwargs: dict[str, Any] = {}
    if category:
        scan_kwargs["FilterExpression"] = Attr("category").eq(category)

    rows: list[dict[str, Any]] = []
    while True:
        resp = table.scan(**scan_kwargs)
        rows.extend(resp.get("Items", []))
        key = resp.get("LastEvaluatedKey")
        if not key or len(rows) >= limit:
            break
        scan_kwargs["ExclusiveStartKey"] = key

    items = sorted(
        (_display(r) for r in rows),
        key=lambda i: (i["deal_price"] is None, i["title"]),
    )[:limit]
    return respond(200, {
        "category": category or None,
        "count": len(items),
        "currency": "USD",
        "items": items,
    })

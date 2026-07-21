"""GET | POST | DELETE /api/bag - CRUD on the adidlabs-bag DynamoDB table.

Table ``adidlabs-bag`` (PAY_PER_REQUEST): pk ``user_id``, sk ``item_id``.
The user_id is ALWAYS derived from the JWT ``sub`` claim (never the request
body) - architecture Sec. 6. This mirrors the MCP ``bag_add`` / ``bag_get``
tool semantics so the storefront and the agents read/write the same rows.

  GET    /api/bag            -> list the caller's bag rows (bag_get)
  POST   /api/bag {item...}  -> add / upsert a row, qty accumulates (bag_add)
  DELETE /api/bag?item_id=X  -> remove one row

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Mapping

import boto3
from boto3.dynamodb.conditions import Key

from common.http import (
    error,
    get_method,
    get_query,
    get_user_id,
    parse_body,
    preflight,
    respond,
)

_LOG = logging.getLogger(__name__)

_TABLE_ENV = "BAG_TABLE"


def _table():
    """Return the DynamoDB bag Table resource (region ap-southeast-2)."""
    name = os.environ.get(_TABLE_ENV, "adidlabs-bag")
    ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ap-southeast-2"))
    return ddb.Table(name)


def _clean(obj: Any) -> Any:
    """Recursively convert DynamoDB ``Decimal`` values to int/float for JSON."""
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        # Whole numbers -> int, otherwise float (prices carry cents).
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


def _get_bag(user_id: str) -> dict[str, Any]:
    """Query all rows for a user (bag_get semantics)."""
    resp = _table().query(KeyConditionExpression=Key("user_id").eq(user_id))
    items = _clean(resp.get("Items", []))
    subtotal = 0.0
    total_qty = 0
    for it in items:
        price = it.get("price") or 0
        qty = it.get("qty") or 1
        subtotal += float(price) * int(qty)
        total_qty += int(qty)
    # "count" = number of distinct line items (matches the frontend bag badge,
    # which renders items.length); "total_qty" = sum of per-line quantities.
    # Keeping both fields explicit stops the two notions being conflated —
    # e.g. one line item with qty 2 is count=1, total_qty=2. "subtotal" is
    # price * qty summed.
    return {
        "user_id": user_id,
        "items": items,
        "count": len(items),
        "total_qty": total_qty,
        "subtotal": round(subtotal, 2),
    }


def _add_item(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Upsert a bag row, accumulating qty on repeat adds (bag_add semantics)."""
    item_id = body.get("item_id")
    if not item_id:
        raise ValueError("item_id is required")

    qty = int(body.get("qty", 1) or 1)
    if qty < 1:
        raise ValueError("qty must be >= 1")

    # Prices are synthetic EUR from the mock catalog; store as Decimal for DDB.
    price = body.get("price")

    # Descriptive fields (title/category/price/image) are only overwritten when
    # the caller actually supplies them. A repeat add that sends just
    # ``{item_id, qty}`` must accumulate qty WITHOUT clobbering the existing
    # row's title/category with empty strings. When a field is present we SET
    # it; when it is absent we seed it via ``if_not_exists`` so a brand-new row
    # still gets a value but an existing row is preserved.
    has_title = "title" in body and body.get("title") not in (None, "")
    has_category = "category" in body and body.get("category") not in (None, "")
    has_image = bool(body.get("image"))

    set_clauses = ["qty = if_not_exists(qty, :zero) + :q"]
    values: dict[str, Any] = {":q": qty, ":zero": 0}

    if has_title:
        set_clauses.append("title = :t")
        values[":t"] = str(body["title"])
    else:
        # Preserve an existing title; initialise new rows to "".
        set_clauses.append("title = if_not_exists(title, :t_empty)")
        values[":t_empty"] = ""

    if has_category:
        set_clauses.append("category = :c")
        values[":c"] = str(body["category"])
    else:
        set_clauses.append("category = if_not_exists(category, :c_empty)")
        values[":c_empty"] = ""

    if price is not None:
        set_clauses.append("price = :p")
        values[":p"] = Decimal(str(price))

    if has_image:
        set_clauses.append("image = :img")
        values[":img"] = body["image"]

    # AI provenance: rows the stylist mesh added automatically carry
    # ai_pick=true (and an optional ai_note label such as "AI CHOICE" for the
    # login auto-kit or "AI ADVICE" for chat-requested adds) so the bag UI can
    # tag them and the user can curate.
    if "ai_pick" in body:
        set_clauses.append("ai_pick = :ai")
        values[":ai"] = bool(body.get("ai_pick"))
    if body.get("ai_note"):
        set_clauses.append("ai_note = :an")
        values[":an"] = str(body["ai_note"])[:40]

    table = _table()
    # Accumulate qty if the row already exists; otherwise this initialises it.
    table.update_item(
        Key={"user_id": user_id, "item_id": str(item_id)},
        UpdateExpression="SET " + ", ".join(set_clauses),
        ExpressionAttributeValues=values,
    )
    return _get_bag(user_id)


def _delete_item(user_id: str, item_id: str) -> dict[str, Any]:
    """Remove a single bag row for the user."""
    if not item_id:
        raise ValueError("item_id is required")
    _table().delete_item(Key={"user_id": user_id, "item_id": str(item_id)})
    return _get_bag(user_id)


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda entry point for /api/bag (GET / POST / DELETE)."""
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()

    user_id = get_user_id(event)

    try:
        if method == "GET":
            return respond(200, _get_bag(user_id))

        if method == "POST":
            body = parse_body(event)
            return respond(200, _add_item(user_id, body))

        if method == "DELETE":
            # Prefer the ?item_id query param; fall back to the body for clients
            # that send it there. Parse the body at most once and reuse it.
            item_id = get_query(event).get("item_id")
            if not item_id:
                item_id = parse_body(event).get("item_id")
            return respond(200, _delete_item(user_id, item_id))

        return error(405, "method not allowed")
    except ValueError as exc:
        return error(400, str(exc))
    except Exception:  # noqa: BLE001 - surface DDB failures as 500 w/ CORS
        # Log the DDB/runtime cause server-side; give the client a generic
        # message so internals are never leaked to the browser.
        _LOG.exception("bag %s operation failed for user_id=%s", method, user_id)
        return error(500, "bag operation failed")

"""POST /api/feedback - thumbs up/down on a catalog product photo.

Anonymous by design: feedback must work for logged-out browsers (the site is
fully browsable without an account), so this route carries no JWT authorizer.
Votes adjust ``feedback_up`` / ``feedback_down`` counters directly on the
catalog row (no per-voter records — the SPA tracks its own vote per browser
in localStorage; good enough for a demo signal).

Votes are reversible: clicking the same thumb again retracts it, clicking
the other thumb switches it. The client reports its previous vote so the
server can move the counters accordingly.

Body: {"item_id": "kt-12345", "vote": "up" | "down" | "none",
       "previous": "up" | "down" | null}
  vote=up|down, previous=null      -> new vote        (+1 vote)
  vote=none,    previous=up|down   -> retract          (-1 previous)
  vote=up|down, previous=the other -> switch           (+1 vote, -1 previous)
Returns: {"item_id": ..., "up": <int>, "down": <int>}

Region: ap-southeast-2 (Sydney).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import os

import boto3
from botocore.exceptions import ClientError

try:  # package-relative (Lambda zip) with direct-run fallback
    from common.http import error, get_method, parse_body, preflight, respond
except ImportError:  # pragma: no cover
    from backend.common.http import error, get_method, parse_body, preflight, respond

_VOTES = {"up": "feedback_up", "down": "feedback_down"}


def _table():
    name = os.environ.get("CATALOG_TABLE", "adidlabs-catalog")
    ddb = boto3.resource(
        "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")
    )
    return ddb.Table(name)


def handler(event, context):  # noqa: ANN001 - Lambda signature
    method = get_method(event)
    if method == "OPTIONS":
        return preflight()
    if method != "POST":
        return error(405, "POST only")

    body = parse_body(event)
    item_id = str(body.get("item_id") or "").strip()
    vote = str(body.get("vote") or "").strip().lower()
    previous = str(body.get("previous") or "").strip().lower() or None
    if not item_id or len(item_id) > 64:
        return error(400, "item_id is required")
    if vote not in (*_VOTES, "none"):
        return error(400, "vote must be 'up', 'down' or 'none'")
    if previous is not None and previous not in _VOTES:
        return error(400, "previous must be 'up', 'down' or omitted")
    if vote == "none" and previous is None:
        return error(400, "retracting requires previous")

    incr = _VOTES[vote] if vote in _VOTES and vote != previous else None
    decr = _VOTES[previous] if previous and previous != vote else None
    if not incr and not decr:  # vote == previous — nothing to change
        return _current(item_id)

    table = _table()
    try:
        resp = _apply(table, item_id, incr, decr, guard_decr=True)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "ConditionalCheckFailedException":
            raise
        # Either the item is unknown, or the decremented counter is already 0
        # (e.g. counters were reset since this browser voted). Distinguish by
        # retrying without the decrement guard when there is an increment;
        # a pure retract on a zero counter is a no-op.
        if not _exists(table, item_id):
            return error(404, "unknown item_id")
        if incr:
            resp = _apply(table, item_id, incr, None, guard_decr=False)
        else:
            return _current(item_id)

    row = resp.get("Attributes", {})
    return respond(200, {
        "item_id": item_id,
        "up": max(0, int(row.get("feedback_up", 0))),
        "down": max(0, int(row.get("feedback_down", 0))),
    })


def _apply(table, item_id: str, incr: str | None, decr: str | None,
           guard_decr: bool):
    """Single UpdateItem moving one or both counters."""
    adds, names = [], {}
    values: dict = {}
    condition = "attribute_exists(item_id)"
    if incr:
        adds.append("#i :one")
        names["#i"] = incr
        values[":one"] = 1
    if decr:
        adds.append("#d :neg")
        names["#d"] = decr
        values[":neg"] = -1
        if guard_decr:
            # Never drive a counter negative (lost browsers, resets).
            condition += " AND #d >= :min"
            values[":min"] = 1
    return table.update_item(
        Key={"item_id": item_id},
        ConditionExpression=condition,
        UpdateExpression="ADD " + ", ".join(adds),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )


def _exists(table, item_id: str) -> bool:
    return bool(table.get_item(
        Key={"item_id": item_id}, ProjectionExpression="item_id"
    ).get("Item"))


def _current(item_id: str):
    row = _table().get_item(Key={"item_id": item_id}).get("Item")
    if not row:
        return error(404, "unknown item_id")
    return respond(200, {
        "item_id": item_id,
        "up": max(0, int(row.get("feedback_up", 0))),
        "down": max(0, int(row.get("feedback_down", 0))),
    })

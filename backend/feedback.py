"""POST /api/feedback - thumbs up/down on a catalog product photo.

Anonymous by design: feedback must work for logged-out browsers (the site is
fully browsable without an account), so this route carries no JWT authorizer.
Votes increment ``feedback_up`` / ``feedback_down`` counters directly on the
catalog row (no per-voter records — the SPA dedupes per browser via
localStorage; good enough for a demo signal).

Body: {"item_id": "kt-12345", "vote": "up" | "down"}
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
    if not item_id or len(item_id) > 64:
        return error(400, "item_id is required")
    if vote not in _VOTES:
        return error(400, "vote must be 'up' or 'down'")

    attr = _VOTES[vote]
    try:
        resp = _table().update_item(
            Key={"item_id": item_id},
            # Only existing catalog rows accumulate votes — reject unknown ids
            # so anonymous traffic cannot create junk rows.
            ConditionExpression="attribute_exists(item_id)",
            UpdateExpression="ADD #a :one",
            ExpressionAttributeNames={"#a": attr},
            ExpressionAttributeValues={":one": 1},
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return error(404, "unknown item_id")
        raise

    row = resp.get("Attributes", {})
    return respond(200, {
        "item_id": item_id,
        "up": int(row.get("feedback_up", 0)),
        "down": int(row.get("feedback_down", 0)),
    })

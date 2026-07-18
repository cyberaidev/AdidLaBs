"""Tests for the bag handler (DynamoDB CRUD) using botocore Stubber.

Happy path: GET queries the bag table and returns items + subtotal.
Error path: a stubbed DynamoDB ClientError surfaces as a 500 (CORS present).

No real AWS calls: the DynamoDB resource's underlying client is stubbed and its
endpoint is never reached (Stubber intercepts before HTTP).

Concept demo - no affiliation with adidas AG. All products fictional.
"""

from __future__ import annotations

import json

import boto3
import pytest
from botocore.stub import ANY, Stubber

import bag
from tests.conftest import assert_cors, http_event


@pytest.fixture
def stubbed_bag_table(monkeypatch):
    """Yield a (Table, Stubber) pair wired into the handler via bag._table.

    We build one DynamoDB resource/table, attach a Stubber to its client, and
    monkeypatch ``bag._table`` to return it so every handler call shares the
    stub.
    """
    resource = boto3.resource("dynamodb", region_name="ap-southeast-2")
    table = resource.Table("adidlabs-bag")
    stubber = Stubber(table.meta.client)
    monkeypatch.setattr(bag, "_table", lambda: table)
    with stubber:
        yield table, stubber


def test_bag_get_happy(stubbed_bag_table):
    """GET returns the caller's rows with a computed subtotal."""
    _table, stubber = stubbed_bag_table
    # boto3's resource layer serializes the Key condition into
    # KeyConditionExpression lazily, so we assert only the table name here and
    # verify the caller scoping via the returned user_id below.
    stubber.add_response(
        "query",
        {
            "Items": [
                {
                    "user_id": {"S": "user-123"},
                    "item_id": {"S": "shoes-1"},
                    "title": {"S": "Cloudstep Runner"},
                    "category": {"S": "shoes"},
                    "price": {"N": "119"},
                    "qty": {"N": "2"},
                }
            ],
            "Count": 1,
        },
        expected_params={"TableName": "adidlabs-bag", "KeyConditionExpression": ANY},
    )

    resp = bag.handler(http_event("GET", sub="user-123"))

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["user_id"] == "user-123"
    assert body["count"] == 1  # distinct line items
    assert body["total_qty"] == 2  # sum of per-line qty (1 line * qty 2)
    assert body["subtotal"] == 238.0  # 119 * 2
    assert body["items"][0]["item_id"] == "shoes-1"


def test_bag_post_add_then_returns_bag(stubbed_bag_table):
    """POST upserts a row (update_item) then re-queries the bag."""
    _table, stubber = stubbed_bag_table
    # 1) the update_item write (upsert with qty accumulation)
    stubber.add_response(
        "update_item",
        {},
        expected_params={
            "TableName": "adidlabs-bag",
            "Key": ANY,
            "UpdateExpression": ANY,
            "ExpressionAttributeValues": ANY,
        },
    )
    # 2) the follow-up query that _add_item performs to return the fresh bag
    stubber.add_response(
        "query",
        {
            "Items": [
                {
                    "user_id": {"S": "user-123"},
                    "item_id": {"S": "jacket-9"},
                    "title": {"S": "Stormline Shell"},
                    "category": {"S": "jacket"},
                    "price": {"N": "149"},
                    "qty": {"N": "1"},
                }
            ],
            "Count": 1,
        },
        expected_params={"TableName": "adidlabs-bag", "KeyConditionExpression": ANY},
    )

    event = http_event(
        "POST",
        sub="user-123",
        body={"item_id": "jacket-9", "title": "Stormline Shell", "category": "jacket", "price": 149},
    )
    resp = bag.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["items"][0]["item_id"] == "jacket-9"
    assert body["subtotal"] == 149.0


def test_bag_post_repeat_add_preserves_title_category(stubbed_bag_table):
    """A repeat add of just {item_id, qty} must NOT clobber title/category.

    When the client omits title/category the UpdateExpression must guard them
    with ``if_not_exists`` (preserving the existing row) rather than SETting
    them to empty strings from ``body.get('title','')``.
    """
    table, stubber = stubbed_bag_table

    # Capture the real update_item call args (Stubber can't match a callable on
    # a single field), then delegate to the stubbed client via the resource.
    captured: dict[str, object] = {}
    real_update = table.update_item

    def _wrapped_update(**kwargs):
        captured["UpdateExpression"] = kwargs.get("UpdateExpression")
        captured["ExpressionAttributeValues"] = kwargs.get("ExpressionAttributeValues")
        return real_update(**kwargs)

    table.update_item = _wrapped_update  # type: ignore[method-assign]

    stubber.add_response(
        "update_item",
        {},
        expected_params={
            "TableName": "adidlabs-bag",
            "Key": {"user_id": "user-123", "item_id": "shoes-1"},
            "UpdateExpression": ANY,
            "ExpressionAttributeValues": ANY,
        },
    )
    stubber.add_response(
        "query",
        {
            "Items": [
                {
                    "user_id": {"S": "user-123"},
                    "item_id": {"S": "shoes-1"},
                    "title": {"S": "Cloudstep Runner"},
                    "category": {"S": "shoes"},
                    "qty": {"N": "3"},
                }
            ],
            "Count": 1,
        },
        expected_params={"TableName": "adidlabs-bag", "KeyConditionExpression": ANY},
    )

    # Repeat add: only item_id + qty, no descriptive fields.
    event = http_event("POST", sub="user-123", body={"item_id": "shoes-1", "qty": 1})
    resp = bag.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    expr = captured["UpdateExpression"]
    vals = captured["ExpressionAttributeValues"]
    # title/category must be preserved via if_not_exists, NOT overwritten.
    assert "title = if_not_exists(title" in expr
    assert "category = if_not_exists(category" in expr
    assert "title = :t" not in expr  # no unconditional overwrite
    assert "category = :c" not in expr
    # No empty-string overwrite values leaked into the SET.
    assert vals.get(":t_empty") == ""
    assert vals.get(":c_empty") == ""
    # qty still accumulates from the existing row.
    assert "qty = if_not_exists(qty, :zero) + :q" in expr
    # The returned row kept its original title/category.
    body = json.loads(resp["body"])
    assert body["items"][0]["title"] == "Cloudstep Runner"
    assert body["items"][0]["category"] == "shoes"


def test_bag_post_missing_item_id_400(stubbed_bag_table):
    """POST without item_id is a 400 before any DDB write."""
    _table, _stubber = stubbed_bag_table
    resp = bag.handler(http_event("POST", sub="user-123", body={"title": "no id"}))
    assert resp["statusCode"] == 400
    assert_cors(resp)


def test_bag_delete_by_query_param(stubbed_bag_table):
    """DELETE ?item_id=X removes the row (delete_item) then returns the bag.

    Exercises the DELETE branch and its query-param item_id resolution.
    """
    _table, stubber = stubbed_bag_table
    # 1) the delete_item write for the targeted row
    stubber.add_response(
        "delete_item",
        {},
        expected_params={
            "TableName": "adidlabs-bag",
            "Key": {"user_id": "user-123", "item_id": "shoes-1"},
        },
    )
    # 2) the follow-up query that _delete_item performs to return the fresh bag
    stubber.add_response(
        "query",
        {"Items": [], "Count": 0},
        expected_params={"TableName": "adidlabs-bag", "KeyConditionExpression": ANY},
    )

    event = http_event("DELETE", sub="user-123", query={"item_id": "shoes-1"})
    resp = bag.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["user_id"] == "user-123"
    assert body["count"] == 0
    assert body["items"] == []
    assert body["subtotal"] == 0.0


def test_bag_delete_item_id_from_body(stubbed_bag_table):
    """DELETE with no query param falls back to item_id in the JSON body.

    Exercises the second ``parse_body(event)`` read in the DELETE branch
    (bag.py:147) when ``queryStringParameters`` carries no item_id.
    """
    _table, stubber = stubbed_bag_table
    stubber.add_response(
        "delete_item",
        {},
        expected_params={
            "TableName": "adidlabs-bag",
            "Key": {"user_id": "user-123", "item_id": "jacket-9"},
        },
    )
    stubber.add_response(
        "query",
        {"Items": [], "Count": 0},
        expected_params={"TableName": "adidlabs-bag", "KeyConditionExpression": ANY},
    )

    # No query param -> handler reads item_id from the body instead.
    event = http_event("DELETE", sub="user-123", body={"item_id": "jacket-9"})
    resp = bag.handler(event)

    assert resp["statusCode"] == 200
    assert_cors(resp)
    body = json.loads(resp["body"])
    assert body["count"] == 0


def test_bag_delete_missing_item_id_400(stubbed_bag_table):
    """DELETE without item_id (query or body) is a 400 before any DDB call."""
    _table, _stubber = stubbed_bag_table
    resp = bag.handler(http_event("DELETE", sub="user-123"))
    assert resp["statusCode"] == 400
    assert_cors(resp)


def test_bag_error_ddb_failure_500(stubbed_bag_table):
    """A DynamoDB ClientError on query surfaces as a 500 with CORS."""
    _table, stubber = stubbed_bag_table
    stubber.add_client_error("query", service_error_code="ResourceNotFoundException")

    resp = bag.handler(http_event("GET", sub="user-123"))

    assert resp["statusCode"] == 500
    assert_cors(resp)
    assert json.loads(resp["body"])["error"] == "bag operation failed"


def test_bag_options_preflight():
    """OPTIONS returns 204 preflight with CORS (no table needed)."""
    resp = bag.handler(http_event("OPTIONS"))
    assert resp["statusCode"] == 204
    assert_cors(resp)

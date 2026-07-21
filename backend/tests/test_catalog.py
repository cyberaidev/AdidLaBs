"""Tests for GET /api/catalog (browse drawers).

Concept demo - no affiliation with adidas AG. All products fictional.
No real DynamoDB calls - the table is stubbed.
"""

from __future__ import annotations

import json
from decimal import Decimal

import catalog


class FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def scan(self, **kwargs):
        return {"Items": self._rows}


ROWS = [
    {"item_id": "hf-1", "name": "Atlas Runner", "category": "shoes",
     "original_price": Decimal("120"), "price": Decimal("90")},
    {"item_id": "hf-2", "name": "Basel Trouser", "category": "pants",
     "original_price": Decimal("80"), "price": Decimal("80")},
]


def _get(query=None):
    return {
        "requestContext": {"http": {"method": "GET"}},
        "queryStringParameters": query or {},
    }


def test_display_maps_deal_pricing():
    item = catalog._display(ROWS[0])
    assert item["title"] == "Atlas Runner"
    assert item["price"] == 120.0
    assert item["deal_price"] == 90.0
    plain = catalog._display(ROWS[1])
    assert plain["price"] == 80.0
    assert plain["deal_price"] is None


def test_handler_returns_items(monkeypatch):
    monkeypatch.setattr(catalog, "_table", lambda: FakeTable(ROWS))
    body = json.loads(catalog.handler(_get({"category": "shoes"}))["body"])
    assert body["currency"] == "USD"
    assert body["count"] == 2  # stub scan ignores the filter; mapping intact
    assert body["items"][0]["deal_price"] is not None  # deals sort first


def test_handler_rejects_unknown_category(monkeypatch):
    monkeypatch.setattr(catalog, "_table", lambda: FakeTable([]))
    assert catalog.handler(_get({"category": "hats"}))["statusCode"] == 400
    assert catalog.handler(_get({"limit": "x"}))["statusCode"] == 400

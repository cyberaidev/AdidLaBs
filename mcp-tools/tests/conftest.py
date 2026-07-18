"""Shared pytest fixtures and boto3/network stubs for the MCP tools tests.

Concept demo - no affiliation with adidas AG. All products fictional.

Nothing here touches real DynamoDB, Bedrock, ddgs, or Tavily. Every external
dependency is replaced with an in-memory fake and injected by monkeypatching the
factory helpers in ``server`` (and ``register_gateway``).
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from typing import Any, Dict, List

import pytest

# Make the module-under-test importable when running `pytest` from mcp-tools/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --------------------------------------------------------------------------- #
# Fake DynamoDB (resource -> Table) with just the operations the tools use.
# --------------------------------------------------------------------------- #

class FakeTable:
    def __init__(self, name: str, items: List[Dict[str, Any]]):
        self.name = name
        # Store copies so tests can mutate their seed lists freely.
        self._items = [dict(i) for i in items]
        self.put_calls: List[Dict[str, Any]] = []

    # get_catalog(item_id=...) and any exact key lookup.
    def get_item(self, Key: Dict[str, Any]):  # noqa: N803 - boto3 casing
        for item in self._items:
            if all(item.get(k) == v for k, v in Key.items()):
                return {"Item": dict(item)}
        return {}

    # get_catalog / get_deals use scan; FilterExpression is a fake condition
    # object (see FakeCondition) that exposes .matches(item).
    #
    # Pagination: if `page_size` was set on this table, scan honours
    # ExclusiveStartKey and returns LastEvaluatedKey so multi-page scan logic
    # (get_deals) can be exercised. FilterExpression is applied *after* paging,
    # exactly like real DynamoDB (Limit/paging is over scanned rows, not
    # matched rows), so a page can legitimately return zero matches.
    page_size = None

    def scan(self, FilterExpression=None, Limit=None, ExclusiveStartKey=None, **_):  # noqa: N803
        rows = self._items

        if self.page_size is not None:
            start = 0
            if ExclusiveStartKey is not None:
                start = int(ExclusiveStartKey.get("_offset", 0))
            page = rows[start : start + self.page_size]
            next_offset = start + self.page_size
            if FilterExpression is not None:
                page = [r for r in page if FilterExpression.matches(r)]
            out: Dict[str, Any] = {"Items": [dict(r) for r in page]}
            if next_offset < len(rows):
                out["LastEvaluatedKey"] = {"_offset": next_offset}
            return out

        if FilterExpression is not None:
            rows = [r for r in rows if FilterExpression.matches(r)]
        if Limit is not None:
            rows = rows[: int(Limit)]
        return {"Items": [dict(r) for r in rows]}

    # bag_get uses query on the pk.
    def query(self, KeyConditionExpression=None, **_):  # noqa: N803
        rows = self._items
        if KeyConditionExpression is not None:
            rows = [r for r in rows if KeyConditionExpression.matches(r)]
        return {"Items": [dict(r) for r in rows]}

    # bag_add writes here.
    def put_item(self, Item: Dict[str, Any]):  # noqa: N803
        self.put_calls.append(dict(Item))
        # Emulate upsert by item_id within same pk.
        key_fields = ("user_id", "item_id")
        self._items = [
            i
            for i in self._items
            if not all(i.get(k) == Item.get(k) for k in key_fields if k in Item)
        ]
        self._items.append(dict(Item))
        return {}


class FakeDynamoResource:
    def __init__(self, tables: Dict[str, FakeTable]):
        self._tables = tables

    def Table(self, name: str) -> FakeTable:  # noqa: N802 - boto3 casing
        # Auto-create empty tables so bag writes to a fresh partition work.
        if name not in self._tables:
            self._tables[name] = FakeTable(name, [])
        return self._tables[name]


# --------------------------------------------------------------------------- #
# Fake boto3.dynamodb.conditions.Attr / Key.
#
# server.py imports Attr/Key inside the functions. We monkeypatch the real
# classes' behaviour by providing a tiny compatible module. Simpler: the real
# boto3 conditions objects are lazily importable and support &; but to keep
# tests free of boto3 we patch them with FakeCondition that supports .eq/.gt/&.
# --------------------------------------------------------------------------- #

class FakeCondition:
    def __init__(self, predicate):
        self._predicate = predicate

    def matches(self, item: Dict[str, Any]) -> bool:
        return self._predicate(item)

    def __and__(self, other: "FakeCondition") -> "FakeCondition":
        return FakeCondition(lambda i: self.matches(i) and other.matches(i))


class FakeAttr:
    def __init__(self, name: str):
        self.name = name

    def eq(self, value):
        return FakeCondition(lambda i: i.get(self.name) == value)

    def gt(self, value):
        return FakeCondition(lambda i: (i.get(self.name) or 0) > value)


class FakeKey:
    def __init__(self, name: str):
        self.name = name

    def eq(self, value):
        return FakeCondition(lambda i: i.get(self.name) == value)


@pytest.fixture(autouse=True)
def patch_boto3_conditions(monkeypatch):
    """Replace boto3.dynamodb.conditions.Attr/Key with in-memory fakes.

    server.py does `from boto3.dynamodb.conditions import Attr` / `Key` inside
    functions, so we patch the attributes on that module. We create a fake
    module if boto3 is not installed at all.
    """
    import types

    try:
        import boto3.dynamodb.conditions as conditions  # type: ignore
        monkeypatch.setattr(conditions, "Attr", FakeAttr, raising=False)
        monkeypatch.setattr(conditions, "Key", FakeKey, raising=False)
    except Exception:
        # boto3 absent: synthesize the module path so the `from ... import` works.
        boto3_mod = sys.modules.setdefault("boto3", types.ModuleType("boto3"))
        ddb_mod = types.ModuleType("boto3.dynamodb")
        cond_mod = types.ModuleType("boto3.dynamodb.conditions")
        cond_mod.Attr = FakeAttr
        cond_mod.Key = FakeKey
        ddb_mod.conditions = cond_mod
        boto3_mod.dynamodb = ddb_mod
        sys.modules["boto3.dynamodb"] = ddb_mod
        sys.modules["boto3.dynamodb.conditions"] = cond_mod
    yield


# --------------------------------------------------------------------------- #
# Seed data + fixtures wiring the fakes into `server`.
# --------------------------------------------------------------------------- #

CATALOG_SEED = [
    {
        "item_id": "sh-001",
        "category": "shoes",
        "title": "Forecast Runner",
        "price": Decimal("120.00"),
        "deal_pct": Decimal("0"),
        "stock": Decimal("14"),
    },
    {
        "item_id": "sh-002",
        "category": "shoes",
        "title": "Storm Trainer",
        "price": Decimal("140.00"),
        "deal_pct": Decimal("30"),
        "stock": Decimal("6"),
    },
    {
        "item_id": "ja-001",
        "category": "jacket",
        "title": "Drizzle Shell",
        "price": Decimal("200.00"),
        "deal_pct": Decimal("15"),
        "stock": Decimal("9"),
    },
    {
        "item_id": "ts-001",
        "category": "tshirt",
        "title": "Base Layer Tee",
        "price": Decimal("35.00"),
        "deal_pct": Decimal("0"),
        "stock": Decimal("40"),
    },
]

BAG_SEED = [
    {"user_id": "user-1", "item_id": "sh-001", "qty": Decimal("1"), "price": Decimal("120.00")},
    {"user_id": "user-1", "item_id": "ja-001", "qty": Decimal("2"), "price": Decimal("200.00")},
    {"user_id": "user-2", "item_id": "ts-001", "qty": Decimal("1"), "price": Decimal("35.00")},
]


@pytest.fixture
def server_module(monkeypatch):
    """Import `server` with env + boto3 factory stubbed for DynamoDB tests."""
    monkeypatch.setenv("CATALOG_TABLE", "adidlabs-catalog")
    monkeypatch.setenv("BAG_TABLE", "adidlabs-bag")

    import server  # imported after sys.path insertion in this file

    tables = {
        "adidlabs-catalog": FakeTable("adidlabs-catalog", CATALOG_SEED),
        "adidlabs-bag": FakeTable("adidlabs-bag", BAG_SEED),
    }
    fake_resource = FakeDynamoResource(tables)
    monkeypatch.setattr(server, "_dynamodb_resource", lambda: fake_resource)

    # Expose the tables so tests can assert on writes.
    server._test_tables = tables  # type: ignore[attr-defined]
    return server

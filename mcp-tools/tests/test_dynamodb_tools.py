"""Tests for the DynamoDB-backed tools: get_catalog, get_deals, bag_add, bag_get.

Concept demo - no affiliation with adidas AG. All products fictional.

All DynamoDB I/O is stubbed via the fakes in conftest.py - no real table calls.
"""

from __future__ import annotations


def test_get_catalog_all_items(server_module):
    result = server_module.get_catalog_impl()
    assert result["source"] == "catalog"
    assert result["count"] == 4
    # Decimals must be normalized to plain numbers.
    prices = {i["item_id"]: i["price"] for i in result["items"]}
    assert prices["sh-001"] == 120
    assert isinstance(prices["sh-001"], (int, float))


def test_get_catalog_by_category(server_module):
    result = server_module.get_catalog_impl(category="Shoes")  # case-insensitive
    assert result["count"] == 2
    assert {i["item_id"] for i in result["items"]} == {"sh-001", "sh-002"}


def test_get_catalog_by_item_id_hit(server_module):
    result = server_module.get_catalog_impl(item_id="ja-001")
    assert result["count"] == 1
    assert result["items"][0]["title"] == "Drizzle Shell"


def test_get_catalog_by_item_id_miss(server_module):
    result = server_module.get_catalog_impl(item_id="nope-999")
    assert result["count"] == 0
    assert result["items"] == []


def test_get_catalog_respects_limit(server_module):
    result = server_module.get_catalog_impl(limit=2)
    assert result["count"] == 2


def test_get_deals_only_discounted_sorted(server_module):
    result = server_module.get_deals_impl()
    assert result["source"] == "deals"
    # Only sh-002 (30%) and ja-001 (15%) have deal_pct > 0.
    ids = [i["item_id"] for i in result["items"]]
    assert ids == ["sh-002", "ja-001"]  # best discount first


def test_get_deals_by_category(server_module):
    result = server_module.get_deals_impl(category="jacket")
    assert result["count"] == 1
    assert result["items"][0]["item_id"] == "ja-001"


def test_bag_get_scoped_to_user_with_subtotal(server_module):
    result = server_module.bag_get_impl(user_id="user-1")
    assert result["ok"] is True
    assert result["count"] == 2
    # 120*1 + 200*2 = 520
    assert result["subtotal"] == 520.0
    assert result["currency"] == "EUR"
    # Never leak other users' rows.
    assert all(i["user_id"] == "user-1" for i in result["items"])


def test_bag_get_requires_user_id(server_module):
    result = server_module.bag_get_impl(user_id="")
    assert result["ok"] is False
    assert result["items"] == []


def test_bag_add_writes_row_and_upserts(server_module):
    add = server_module.bag_add_impl(
        user_id="user-3",
        item_id="sh-002",
        qty=2,
        title="Storm Trainer",
        price=140.0,
        category="Shoes",
    )
    assert add["ok"] is True
    assert add["item"]["qty"] == 2
    assert add["item"]["category"] == "shoes"  # lowercased

    # The stubbed table recorded exactly one put_item.
    bag_table = server_module._test_tables["adidlabs-bag"]
    assert len(bag_table.put_calls) == 1

    # And a subsequent read reflects the write.
    read = server_module.bag_get_impl(user_id="user-3")
    assert read["count"] == 1
    assert read["items"][0]["item_id"] == "sh-002"
    assert read["subtotal"] == 280.0  # 140 * 2


def test_bag_add_validates_inputs(server_module):
    result = server_module.bag_add_impl(user_id="", item_id="x")
    assert result["ok"] is False
    assert "required" in result["error"]


def test_bag_add_clamps_non_positive_qty(server_module):
    """A negative or zero qty must never persist - it would poison the subtotal."""
    neg = server_module.bag_add_impl(
        user_id="user-9", item_id="sh-001", qty=-3, price=120.0
    )
    assert neg["item"]["qty"] == 1  # clamped, not stored as -3

    # And what actually got written to the table is the clamped value.
    bag_table = server_module._test_tables["adidlabs-bag"]
    assert bag_table.put_calls[-1]["qty"] == 1

    read = server_module.bag_get_impl(user_id="user-9")
    assert read["subtotal"] == 120.0  # 120 * 1, never a negative subtotal

    zero = server_module.bag_add_impl(user_id="user-9", item_id="sh-002", qty=0)
    assert zero["item"]["qty"] == 1


def test_get_deals_accumulates_matches_across_scan_pages(server_module):
    """get_deals must return `limit` *matched* deals even when DynamoDB pages the
    scan so that any single page under-returns matches (Limit applies to scanned
    rows, not matched rows). We force a tiny page size on the fake table so deals
    are sparse per page and only accumulate across LastEvaluatedKey follows.
    """
    catalog = server_module._test_tables["adidlabs-catalog"]
    # Page size 1 => each scan page sees exactly one row; only 2 of the 4 seed
    # rows are deals (sh-002, ja-001). A single page would miss at least one.
    catalog.page_size = 1

    result = server_module.get_deals_impl(limit=5)
    ids = [i["item_id"] for i in result["items"]]
    # Both deals surface despite the paging, best discount first.
    assert ids == ["sh-002", "ja-001"]
    assert result["count"] == 2


def test_get_deals_respects_limit_across_pages(server_module):
    """When more matches exist than requested, get_deals caps at `limit`."""
    catalog = server_module._test_tables["adidlabs-catalog"]
    catalog.page_size = 1
    result = server_module.get_deals_impl(limit=1)
    assert result["count"] == 1
    # The single returned deal is the best discount (sh-002 at 30%).
    assert result["items"][0]["item_id"] == "sh-002"

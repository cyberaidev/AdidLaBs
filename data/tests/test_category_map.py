"""Unit tests for the AdidLaBs category mapping + price synthesis.

Run from the repo root:
    python -m pytest data/tests/ -q
or without pytest installed:
    python data/tests/test_category_map.py
"""

from __future__ import annotations

import json
import os
import sys

# Make `category_map` importable whether run via pytest or directly.
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DATA_DIR not in sys.path:
    sys.path.insert(0, DATA_DIR)

from category_map import (  # noqa: E402
    CATEGORIES,
    build_item,
    map_category,
    synthesize_name,
    synthesize_price,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "hf_rows_sample.json")


def _load_rows():
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)["rows"]


# --------------------------------------------------------------------------- #
# Mapping correctness
# --------------------------------------------------------------------------- #
def test_fixture_rows_map_to_expected_category():
    """Every fixture row maps to its declared expected_category."""
    for row in _load_rows():
        assert map_category(row) == row["expected_category"], (
            f"row {row['id']} ({row.get('articleType')!r}) "
            f"mapped to {map_category(row)!r}, expected {row['expected_category']!r}"
        )


def test_all_six_categories_covered_by_fixture():
    """The fixture exercises all six contract categories at least once."""
    mapped = {map_category(r) for r in _load_rows()}
    mapped.discard(None)
    assert mapped == set(CATEGORIES), (
        f"fixture covers {sorted(mapped)}, expected {sorted(CATEGORIES)}"
    )


def test_categories_constant_is_the_six():
    assert set(CATEGORIES) == {"shoes", "pants", "tshirt", "jumper", "jacket", "accessory"}
    assert len(CATEGORIES) == 6


def test_article_type_is_case_insensitive():
    assert map_category({"id": "x", "articleType": "SPORTS SHOES"}) == "shoes"
    assert map_category({"id": "x", "articleType": "sports shoes"}) == "shoes"
    assert map_category({"id": "x", "articleType": "Sports Shoes"}) == "shoes"


def test_subcategory_fallback():
    row = {"id": "x", "articleType": "TotallyNovelType", "subCategory": "Bottomwear"}
    assert map_category(row) == "pants"


def test_mastercategory_fallback():
    row = {"id": "x", "articleType": "Unknown", "subCategory": "Unknown",
           "masterCategory": "Footwear"}
    assert map_category(row) == "shoes"


def test_keyword_heuristic_last_resort():
    row = {"id": "x", "articleType": "Chunky Snow Boot"}
    assert map_category(row) == "shoes"


def test_unmappable_returns_none():
    assert map_category({"id": "x", "articleType": "Deodorant",
                         "subCategory": "Fragrance",
                         "masterCategory": "Personal Care"}) is None
    assert map_category({"id": "x"}) is None
    assert map_category({}) is None


# --------------------------------------------------------------------------- #
# Price synthesis
# --------------------------------------------------------------------------- #
def test_price_is_deterministic():
    a = synthesize_price("hf-1001", "shoes")
    b = synthesize_price("hf-1001", "shoes")
    assert a == b, "price synthesis must be deterministic in item_id"


def test_price_within_category_band():
    bands = {
        "shoes": (49, 189), "pants": (29, 129), "tshirt": (15, 59),
        "jumper": (39, 149), "jacket": (69, 259), "accessory": (9, 89),
    }
    for cat, (lo, hi) in bands.items():
        p = synthesize_price(f"hf-seed-{cat}", cat)
        assert lo <= p["original_price"] <= hi + 1, (
            f"{cat} original {p['original_price']} outside band {lo}-{hi}"
        )
        assert p["currency"] == "EUR"


def test_deal_price_le_original_and_pct_consistent():
    for i in range(200):
        p = synthesize_price(f"hf-item-{i}", CATEGORIES[i % 6])
        assert p["price"] <= p["original_price"] + 1e-9
        if p["on_deal"]:
            assert p["discount_pct"] > 0
            assert p["price"] < p["original_price"]
        else:
            assert p["discount_pct"] == 0
            assert p["price"] == p["original_price"]


def test_some_items_are_on_deal():
    """The corpus should contain a healthy mix of deals (not all/none)."""
    deals = sum(
        1 for i in range(300)
        if synthesize_price(f"hf-mix-{i}", CATEGORIES[i % 6])["on_deal"]
    )
    assert 0 < deals < 300, f"expected a mix of deals, got {deals}/300"


# --------------------------------------------------------------------------- #
# build_item end-to-end
# --------------------------------------------------------------------------- #
def test_build_item_shape_and_id_prefix():
    row = {"id": "42", "articleType": "Tshirts", "subCategory": "Topwear",
           "gender": "Men", "season": "Summer", "baseColour": "Red",
           "usage": "Casual", "productDisplayName": "Red Tee"}
    item = build_item(row)
    assert item is not None
    assert item["item_id"] == "hf-42"
    assert item["category"] == "tshirt"
    assert item["currency"] == "EUR"
    for key in ("name", "price", "original_price", "on_deal", "discount_pct",
                "gender", "season", "base_colour", "usage", "source"):
        assert key in item


def test_build_item_discards_upstream_brand_name():
    """The real HF productDisplayName (brand names) must NOT surface."""
    row = {"id": "99", "articleType": "Sandals", "baseColour": "Black",
           "productDisplayName": "ADIDAS Men Spry M Black Sandals"}
    item = build_item(row)
    assert item is not None
    name_lower = item["name"].lower()
    for brand in ("adidas", "nike", "puma", "reebok", "spry"):
        assert brand not in name_lower, f"brand token {brand!r} leaked into name {item['name']!r}"


def test_synthesize_name_is_deterministic_and_brand_safe():
    a = synthesize_name("hf-1", "shoes", "Black")
    b = synthesize_name("hf-1", "shoes", "Black")
    assert a == b
    # A recognised colour word is woven in; unknown 'brandish' colour is dropped.
    assert "Black" in synthesize_name("hf-2", "jacket", "black")
    assert "Adidas" not in synthesize_name("hf-3", "jacket", "adidas-teamblue")


def test_build_item_drops_unmappable_and_missing_id():
    assert build_item({"id": "1", "articleType": "Deodorant",
                       "masterCategory": "Personal Care"}) is None
    assert build_item({"articleType": "Tshirts"}) is None  # no id


def test_build_item_synthesizes_name_without_display_name():
    item = build_item({"id": "7", "articleType": "Watches"})
    assert item is not None
    assert item["name"]  # a fictional name is always produced
    assert item["category"] == "accessory"


# --------------------------------------------------------------------------- #
# Directly-runnable harness (no pytest required)
# --------------------------------------------------------------------------- #
def _run_all():
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {exc!r}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())

"""Tests for the per-category minimum-count target in fetch_hf.fetch_from_hf.

The upstream HuggingFace dataset is heavily skewed (lots of tshirt/accessory/
shoes, very few jumper/jacket). fetch_from_hf must therefore require a *minimum
count per category* — not just presence of all six — and keep paging deep enough
to satisfy the sparse buckets, then trim back toward `target` without dropping
any category below its floor. If the floor cannot be reached it must raise, so
the caller falls back to the synthetic catalog.

These tests drive that logic with a synthetic, skewed page source (no network).

Run:
    python -m pytest data/tests/test_fetch_hf_floor.py -q
or directly:
    python data/tests/test_fetch_hf_floor.py
"""

from __future__ import annotations

import os
import sys

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DATA_DIR not in sys.path:
    sys.path.insert(0, DATA_DIR)

import fetch_hf  # noqa: E402
from category_map import CATEGORIES  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic, skewed "dataset" that mirrors the real HF distribution: common
# categories are dense, jumper/jacket trickle in only on deeper pages.
# --------------------------------------------------------------------------- #
# articleType tokens that category_map maps deterministically to each category.
_ARTICLE_FOR = {
    "shoes": "Casual Shoes",
    "pants": "Jeans",
    "tshirt": "Tshirts",
    "jumper": "Sweaters",
    "jacket": "Jackets",
    "accessory": "Watches",
}


def _make_skewed_dataset(n_pages: int, per_page: int,
                         sparse_every: int) -> list:
    """Build a flat list of raw HF-style rows.

    Common categories (shoes/pants/tshirt/accessory) appear on every page; the
    sparse ones (jumper/jacket) appear only once every `sparse_every` rows, so
    they accumulate slowly — just like the real dataset.
    """
    common = ["tshirt", "accessory", "shoes", "tshirt", "accessory", "pants"]
    rows = []
    rid = 0
    for _ in range(n_pages * per_page):
        rid += 1
        if rid % sparse_every == 0:
            cat = "jumper" if (rid // sparse_every) % 2 == 0 else "jacket"
        else:
            cat = common[rid % len(common)]
        rows.append({
            "id": str(rid),
            "articleType": _ARTICLE_FOR[cat],
            "baseColour": "Black",
            "gender": "Unisex",
            "season": "All",
            "usage": "Casual",
        })
    return rows


def _install_fake_pager(monkeypatch_rows, page_size):
    """Return a _fetch_page replacement that serves monkeypatch_rows in pages."""
    def _fake_fetch_page(offset, length):
        return monkeypatch_rows[offset:offset + length]
    return _fake_fetch_page


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def _patch(rows):
    fetch_hf._fetch_page = _install_fake_pager(rows, fetch_hf.PAGE_SIZE)
    # Never sleep in tests.
    fetch_hf.time.sleep = lambda *_a, **_k: None


def test_floor_met_after_deep_paging():
    """Sparse jumper/jacket still clear the floor because we page deep enough."""
    rows = _make_skewed_dataset(n_pages=30, per_page=fetch_hf.PAGE_SIZE,
                                sparse_every=25)
    _patch(rows)

    items = fetch_hf.fetch_from_hf(target=200, min_per_category=6)

    counts = fetch_hf._counts_by_category(items)
    for cat in CATEGORIES:
        assert counts[cat] >= 6, f"category {cat} below floor: {counts}"


def test_trim_keeps_target_and_preserves_floor():
    """Overshoot on common categories is trimmed back toward target, floor intact."""
    rows = _make_skewed_dataset(n_pages=30, per_page=fetch_hf.PAGE_SIZE,
                                sparse_every=25)
    _patch(rows)

    target = 150
    items = fetch_hf.fetch_from_hf(target=target, min_per_category=6)

    # Trimmed close to target (never below it — we only trim surplus).
    assert len(items) <= target + 1
    assert len(items) >= target - 6 * len(CATEGORIES)  # sanity lower bound
    counts = fetch_hf._counts_by_category(items)
    for cat in CATEGORIES:
        assert counts[cat] >= 6, f"trim dropped {cat} below floor: {counts}"


def test_all_ids_unique_after_trim():
    rows = _make_skewed_dataset(n_pages=30, per_page=fetch_hf.PAGE_SIZE,
                                sparse_every=25)
    _patch(rows)
    items = fetch_hf.fetch_from_hf(target=180, min_per_category=6)
    ids = [it["item_id"] for it in items]
    assert len(ids) == len(set(ids)), "duplicate item_ids after fetch/trim"


def test_unreachable_floor_raises():
    """If a category can never reach the floor, fetch raises (=> caller falls back)."""
    # jacket appears essentially never in this dataset.
    common = ["tshirt", "accessory", "shoes", "pants", "jumper"]
    rows = []
    for rid in range(1, 3001):
        cat = common[rid % len(common)]
        rows.append({
            "id": str(rid),
            "articleType": _ARTICLE_FOR[cat],
            "baseColour": "Black",
        })
    _patch(rows)

    raised = False
    try:
        fetch_hf.fetch_from_hf(target=200, min_per_category=6)
    except RuntimeError as exc:
        raised = True
        assert "jacket" in str(exc).lower() or "floor" in str(exc).lower()
    assert raised, "expected RuntimeError when a category cannot meet the floor"


def test_build_catalog_falls_back_on_unreachable_floor():
    """build_catalog converts the floor RuntimeError into the synthetic fallback."""
    common = ["tshirt", "accessory", "shoes", "pants", "jumper"]
    rows = [{"id": str(rid), "articleType": _ARTICLE_FOR[common[rid % len(common)]],
             "baseColour": "Black"} for rid in range(1, 3001)]
    _patch(rows)

    items, source = fetch_hf.build_catalog(target=200)
    assert source == "fallback", "unreachable floor must trigger the synthetic fallback"
    assert items, "fallback catalog must be non-empty"
    # Fallback itself must cover all six categories.
    covered = {it["category"] for it in items}
    assert covered == set(CATEGORIES), f"fallback missing categories: {set(CATEGORIES) - covered}"


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

#!/usr/bin/env python3
"""Fetch ~200 metadata rows from the HuggingFace fashion dataset.

Source: ``ashraq/fashion-product-images-small`` via the HuggingFace
**datasets-server rows REST API** (NOT the `datasets` Python library — we keep
deps to ``requests`` only, no Arrow/pandas download).

Rows API:
    https://datasets-server.huggingface.co/rows
        ?dataset=ashraq/fashion-product-images-small
        &config=default&split=train&offset=<n>&length=<=100>

We paginate politely (100 rows/page, small sleep, per-request timeout), map each
row to one of the six contract categories (:mod:`category_map`), synthesize EUR
prices/deals, and require a **per-category minimum count** (not just presence) so
the sparse jumper/jacket buckets are not starved — we keep paging deeper until
every category clears its floor, then trim back toward ``target``. On ANY failure
(network, HTTP, empty sample, a category missing, or the floor unreachable within
the page cap) we fall back to ``synthetic_fallback.json``.

Output: ``data/catalog.json`` (list of normalized items) — consumed by
``seed_dynamodb.py`` and ``gen_kb_docs.py``.

Usage:
    python data/fetch_hf.py [--target 200] [--out data/catalog.json] [--force-fallback]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

from category_map import CATEGORIES, build_item

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - requests is the only runtime dep
    requests = None  # noqa: N816

HERE = os.path.dirname(os.path.abspath(__file__))
FALLBACK_PATH = os.path.join(HERE, "synthetic_fallback.json")

DATASET = "ashraq/fashion-product-images-small"
CONFIG = "default"
SPLIT = "train"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE = 100          # datasets-server caps `length` at 100
REQUEST_TIMEOUT = 15     # seconds, polite per-request timeout
PAGE_SLEEP = 0.4         # seconds between pages, be a good citizen
MAX_PAGES = 40           # hard cap so we never loop forever

# Per-category floor. The upstream dataset is heavily skewed toward tshirt /
# accessory / shoes, with jumper and jacket in the long tail — a simple "stop at
# `target` total" pass fills up on the common categories and lands only a
# handful of jumpers/jackets, which starves the RAG corpus and the
# weather-to-outfit picks for cool/cold/rain scenarios that lean on those two.
# So instead of only checking *presence* of all six, we require at least this
# many items per category before we're satisfied (and keep paging deeper to
# reach the sparse ones). If the floor can't be met within MAX_PAGES we raise,
# and the caller falls back to synthetic_fallback.json — same failure contract
# as the old presence guard.
MIN_PER_CATEGORY = 6


def _fetch_page(offset: int, length: int) -> List[Dict[str, Any]]:
    """Fetch one page of rows; returns the list of `row` dicts (may be empty)."""
    if requests is None:
        raise RuntimeError("requests is not installed")
    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "offset": offset,
        "length": length,
    }
    resp = requests.get(ROWS_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("rows", [])
    # Each entry is {"row_idx": int, "row": {...}, "truncated_cells": [...]}.
    return [entry.get("row", {}) for entry in rows]


def _counts_by_category(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {c: 0 for c in CATEGORIES}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    return counts


def _floor_met(items: List[Dict[str, Any]], min_per_category: int) -> bool:
    """True once every one of the six categories has >= min_per_category items."""
    counts = _counts_by_category(items)
    return all(counts[c] >= min_per_category for c in CATEGORIES)


def _trim_to_target(items: List[Dict[str, Any]], target: int,
                    min_per_category: int) -> List[Dict[str, Any]]:
    """Trim to ~target items WITHOUT dropping any category below its floor.

    Paging deep enough to satisfy the sparse categories can overshoot `target`
    on the common ones. We drop surplus items from the largest categories first,
    always keeping at least `min_per_category` in every bucket, so the returned
    catalog stays near `target` while preserving the per-category floor.
    """
    if len(items) <= target:
        return items

    counts = _counts_by_category(items)
    # How many we may remove from each category (never below the floor).
    removable = {c: max(0, counts[c] - min_per_category) for c in CATEGORIES}
    to_remove = len(items) - target

    drop_ids: set[str] = set()
    # Walk items from the end (later pages) so we prefer trimming deeper samples;
    # remove from a category only while it has removable surplus.
    for it in reversed(items):
        if to_remove <= 0:
            break
        cat = it["category"]
        if removable.get(cat, 0) > 0:
            drop_ids.add(it["item_id"])
            removable[cat] -= 1
            to_remove -= 1

    return [it for it in items if it["item_id"] not in drop_ids]


def fetch_from_hf(target: int,
                  min_per_category: int = MIN_PER_CATEGORY) -> List[Dict[str, Any]]:
    """Page through the rows API until every category meets its floor.

    Unlike a plain "stop at `target` total" pass, this keeps paging until BOTH:
      * total mapped items >= ``target``, and
      * every one of the six categories has >= ``min_per_category`` items,
    then trims back toward ``target`` without violating the per-category floor.

    Raises on any network/HTTP error, if the sample is empty, or if the
    per-category floor cannot be reached within ``MAX_PAGES`` — the caller
    converts any of these into a fallback.
    """
    items: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    offset = 0
    pages = 0

    while pages < MAX_PAGES:
        rows = _fetch_page(offset, PAGE_SIZE)
        if not rows:
            break  # reached end of dataset
        for row in rows:
            item = build_item(row)
            if item is None:
                continue
            if item["item_id"] in seen_ids:
                continue
            seen_ids.add(item["item_id"])
            items.append(item)
        offset += PAGE_SIZE
        pages += 1
        # Done only when we have enough total AND every category clears its floor;
        # otherwise keep paging (the sparse jumper/jacket buckets need depth).
        if len(items) >= target and _floor_met(items, min_per_category):
            break
        time.sleep(PAGE_SLEEP)

    if not items:
        raise RuntimeError("HF sample produced zero mapped items")

    covered = {it["category"] for it in items}
    missing = set(CATEGORIES) - covered
    if missing:
        raise RuntimeError(
            f"HF sample did not cover all six categories; missing: {sorted(missing)}"
        )
    if not _floor_met(items, min_per_category):
        counts = _counts_by_category(items)
        short = {c: counts[c] for c in CATEGORIES if counts[c] < min_per_category}
        raise RuntimeError(
            f"HF sample did not meet the per-category floor of {min_per_category}; "
            f"short categories: {short}"
        )

    return _trim_to_target(items, target, min_per_category)


def load_fallback() -> List[Dict[str, Any]]:
    """Load the handwritten synthetic fallback catalog."""
    with open(FALLBACK_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return list(payload.get("items", []))


def build_catalog(target: int, force_fallback: bool = False) -> tuple[List[Dict[str, Any]], str]:
    """Return (items, source) where source is 'huggingface' or 'fallback'."""
    if force_fallback:
        return load_fallback(), "fallback"
    try:
        items = fetch_from_hf(target)
        return items, "huggingface"
    except Exception as exc:  # noqa: BLE001 - any failure => fallback
        print(f"[fetch_hf] HF fetch failed ({exc!r}); using synthetic fallback.",
              file=sys.stderr)
        return load_fallback(), "fallback"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch AdidLaBs mock catalog.")
    parser.add_argument("--target", type=int, default=200,
                        help="Number of items to sample from HF (default 200).")
    parser.add_argument("--out", default=os.path.join(HERE, "catalog.json"),
                        help="Output JSON path (default data/catalog.json).")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Skip HF entirely and use synthetic_fallback.json.")
    args = parser.parse_args(argv)

    items, source = build_catalog(args.target, args.force_fallback)

    by_cat: Dict[str, int] = {c: 0 for c in CATEGORIES}
    for it in items:
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)

    print(f"[fetch_hf] source={source} items={len(items)} -> {args.out}")
    print(f"[fetch_hf] by category: {by_cat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

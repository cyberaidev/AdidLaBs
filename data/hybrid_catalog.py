"""Hybrid catalog build: H&M garments + Polyvore shoes/accessories.

Sources (both ungated HuggingFace datasets):
  * tomytjandra/h-and-m-fashion-caption — 20k modern H&M studio photos
    (~1166x1750). Caption text only, no category column -> Claude Haiku
    vision on Bedrock assigns the section (same pass as rebuild_catalog).
    Supplies the four garment sections + caps/hats/belts/bags.
  * Marqo/polyvore — 94k product cutouts (~300x400) with category labels
    (Sneakers, Boots, Watches, Sunglasses, Backpacks, ...). Supplies SHOES
    and the rest of ACCESSORY. Vision still verifies every pick.

Keyword/category harvest leans streetwear (hoodies, bombers, joggers,
cargo, sneakers, caps, backpacks) per Stefano's Culture-Kings-style brief.

Branded rows (``brand`` attribute — the adidas/Nike/Puma/Reebok items) in
the existing catalog are KEPT. Everything else is replaced.

Usage:
    python data/hybrid_catalog.py --bucket <site-bucket> [--seed] \
        [--table adidlabs-catalog] [--region ap-southeast-2]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from category_map import synthesize_price  # noqa: E402
from rebuild_catalog import (  # noqa: E402
    FILTER_URL, IMG_PREFIX, process_candidate, synthesize_name_from_noun,
)

HM_DATASET = "tomytjandra/h-and-m-fashion-caption"
PV_DATASET = "Marqo/polyvore"

# H&M caption keywords per target section (captions are lowercase).
HM_HARVEST: dict[str, list[str]] = {
    "tshirt": ["t-shirt", "printed motif", "jersey top", "polo", "tee in"],
    "jumper": ["hoodie", "sweatshirt", "jumper", "sweater", "cardigan"],
    "jacket": ["bomber", "windbreaker", "jacket", "parka", "padded"],
    "pants": ["joggers", "cargo", "jeans", "shorts", "sweatpants", "trousers"],
    "accessory": ["cap with", "bucket hat", "beanie", "belt with", "backpack",
                  "shoulder bag"],
}
HM_PER_KEYWORD = 12
HM_TARGETS = {"tshirt": 34, "jumper": 34, "jacket": 34, "pants": 34,
              "accessory": 17}

# Polyvore harvest by its own category labels -> our section.
PV_HARVEST: list[tuple[str, str, int]] = [  # (pv category, section, candidates)
    ("Sneakers", "shoes", 30), ("Boots", "shoes", 14), ("Sandals", "shoes", 10),
    ("Backpacks", "accessory", 10), ("Watches", "accessory", 10),
    # Sunglasses dropped from the range per Stefano (2026-08-03).
]
PV_TARGETS = {"shoes": 34, "accessory": 17}

BRAND_TOKENS = ("adidas", "nike", "puma", "reebok", "converse", "vans",
                "new balance")


def _filter(session: requests.Session, dataset: str, split: str, where: str,
            limit: int) -> list[dict]:
    params = {"dataset": dataset, "config": "default", "split": split,
              "where": where, "limit": limit}
    for attempt in range(8):
        try:
            r = session.get(FILTER_URL, params=params, timeout=90)
            if r.ok and "rows" in r.json():
                return r.json()["rows"]
        except requests.RequestException as exc:
            print(f"[harvest] retry {attempt + 1}: {exc.__class__.__name__}")
        time.sleep(3 * (attempt + 1))  # index warmup / throttling / timeouts
    print(f"[harvest] WARN gave up: {dataset} where={where[:50]}")
    return []


def harvest_hm(session: requests.Session) -> list[dict]:
    out: dict[str, dict] = {}
    for section, keywords in HM_HARVEST.items():
        for kw in keywords:
            rows = _filter(session, HM_DATASET, "train",
                           f"\"text\" LIKE '%{kw}%'", HM_PER_KEYWORD)
            for row in rows:
                rid = f"hm-{row['row_idx']}"
                if rid not in out:
                    out[rid] = {
                        "id": str(row["row_idx"]),
                        "item_id": rid,
                        "source_ds": HM_DATASET,
                        "pool": "hm",
                        "name": row["row"]["text"][:120],
                        "colour": "", "season": "", "usage": "casual",
                        "gender": "",
                        "img_src": row["row"]["image"]["src"],
                    }
        print(f"[hm] {section}: pool now {len(out)}")
    return list(out.values())


def harvest_pv(session: requests.Session) -> list[dict]:
    out: dict[str, dict] = {}
    for pv_cat, _section, n in PV_HARVEST:
        rows = _filter(session, PV_DATASET, "data",
                       f"\"category\"='{pv_cat}'", n)
        for row in rows:
            rr = row["row"]
            rid = "pv-" + str(rr["item_ID"]).replace("_", "-")
            if rid not in out:
                out[rid] = {
                    "id": str(rr["item_ID"]),
                    "item_id": rid,
                    "source_ds": PV_DATASET,
                    "pool": "pv",
                    "name": str(rr.get("text") or pv_cat)[:120],
                    "colour": "", "season": "", "usage": "casual",
                    "gender": "",
                    "img_src": rr["image"]["src"],
                }
        print(f"[pv] {pv_cat}: pool now {len(out)}")
    return list(out.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--table", default="adidlabs-catalog")
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    args = ap.parse_args()

    with open(args.catalog, encoding="utf-8") as fh:
        old_catalog = json.load(fh)
    branded_keep = [i for i in old_catalog if i.get("brand")]
    print(f"[keep] {len(branded_keep)} branded rows retained")

    session = requests.Session()
    hm_pool = harvest_hm(session)
    pv_pool = harvest_pv(session)
    print(f"[pool] hm={len(hm_pool)} pv={len(pv_pool)}")

    verified: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_candidate, c, args.region): c
                for c in hm_pool + pv_pool}
        done = 0
        for fut in as_completed(futs):
            done += 1
            row = fut.result()
            if row:
                # Aesthetic split: polyvore only fills shoes/accessory,
                # H&M never fills shoes (dataset has none anyway).
                if row["pool"] == "pv" and row["category"] not in PV_TARGETS:
                    row = None
                elif row["pool"] == "hm" and row["category"] == "shoes":
                    row = None
            if row:
                verified.append(row)
            if done % 40 == 0:
                print(f"[classify] {done}/{len(futs)} verified={len(verified)}")

    targets = {"tshirt": 34, "jumper": 34, "jacket": 34, "pants": 34,
               "shoes": 34, "accessory": 34}
    buckets: dict[str, list[dict]] = {c: [] for c in targets}
    for r in sorted(verified, key=lambda r: (r["pool"], r["id"])):
        buckets[r["category"]].append(r)
    # Accessory: interleave the two pools so the section mixes H&M caps/belts
    # with polyvore watches/backpacks.
    acc_hm = [r for r in buckets["accessory"] if r["pool"] == "hm"]
    acc_pv = [r for r in buckets["accessory"] if r["pool"] == "pv"]
    mixed = []
    while (acc_hm or acc_pv) and len(mixed) < targets["accessory"]:
        if acc_hm:
            mixed.append(acc_hm.pop(0))
        if acc_pv and len(mixed) < targets["accessory"]:
            mixed.append(acc_pv.pop(0))
    buckets["accessory"] = mixed

    s3 = boto3.client("s3", region_name=args.region)
    items: list[dict] = []
    for cat, want in targets.items():
        chosen = buckets[cat][:want]
        if len(chosen) < want:
            print(f"[select] WARN {cat}: only {len(chosen)}/{want}")
        for r in chosen:
            item_id = r["item_id"]
            colour = r["vision_colour"] or r["colour"]
            s3.put_object(
                Bucket=args.bucket, Key=f"{IMG_PREFIX}/{item_id}.jpg",
                Body=r["hosted_bytes"], ContentType="image/jpeg",
                CacheControl="public,max-age=31536000,immutable",
            )
            brand = next((b for b in BRAND_TOKENS
                          if re.search(rf"\b{b}\b", r["name"].lower())), None)
            items.append({
                "item_id": item_id,
                "category": cat,
                "name": synthesize_name_from_noun(item_id, cat, colour,
                                                  r["noun"]),
                "base_colour": colour,
                "season": r["season"] or "all-season",
                "usage": r["usage"] or "casual",
                "article_type": r["noun"].lower(),
                "gender": r["gender"],
                **({"brand": brand} if brand else {}),
                "source": f"huggingface:{r['source_ds']}",
                "image_url": f"/{IMG_PREFIX}/{item_id}.jpg",
                **synthesize_price(item_id, cat),
            })
    print(f"[select] {len(items)} hybrid items rehosted "
          f"({sum(1 for i in items if i.get('brand'))} with brand tokens)")

    final = items + branded_keep
    with open(args.catalog, "w", encoding="utf-8") as fh:
        json.dump(final, fh, indent=1)
    print(f"[out] wrote {args.catalog} (total {len(final)})")

    if args.seed:
        from decimal import Decimal
        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
        old_ids, kwargs = [], {"ProjectionExpression": "item_id"}
        while True:
            page = table.scan(**kwargs)
            old_ids += [i["item_id"] for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        with table.batch_writer(overwrite_by_pkeys=["item_id"]) as batch:
            for item in final:
                batch.put_item(Item=json.loads(json.dumps(item), parse_float=Decimal))
        keep_ids = {i["item_id"] for i in final}
        stale = [i for i in old_ids if i not in keep_ids]
        with table.batch_writer() as batch:
            for iid in stale:
                batch.delete_item(Key={"item_id": iid})
        print(f"[seed] {len(final)} rows written, {len(stale)} old rows deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Append branded items (adidas / Nike / Puma / Reebok) to the catalog.

Per Stefano's direction the catalog shows real dataset product photographs —
including branded goods — while AdidLaBs' own titles stay fictional. This
script harvests candidates from ktrinh38/fashion-dataset by ``brandName``,
verifies each photo's category with the same Claude-Haiku-vision pass as
data/rebuild_catalog.py, and APPENDS the selected items to data/catalog.json
+ DynamoDB (no deletions). Rows carry a ``brand`` attribute for display.

Usage:
    python data/add_brand_items.py --bucket <site-bucket> [--seed] \
        [--per-brand 8] [--table adidlabs-catalog] [--region ap-southeast-2]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from category_map import synthesize_price  # noqa: E402
from rebuild_catalog import (  # noqa: E402
    CATEGORIES, DATASET, FILTER_URL, IMG_PREFIX, process_candidate,
    synthesize_name_from_noun,
)

# Exact brandName values present in the dataset (case-sensitive filter).
BRAND_SPELLINGS = {
    "adidas": ["ADIDAS", "Adidas"],
    "nike": ["Nike"],
    "puma": ["Puma"],
    "reebok": ["Reebok"],
}


def harvest_brand(session: requests.Session, spellings: list[str],
                  limit: int) -> list[dict]:
    rows: dict[str, dict] = {}
    for spelling in spellings:
        params = {
            "dataset": DATASET, "config": "default", "split": "train",
            "where": f"\"brandName\"='{spelling}' AND \"ageGroup\" LIKE 'Adults%'",
            "limit": limit,
        }
        for attempt in range(5):
            r = session.get(FILTER_URL, params=params, timeout=60)
            if r.ok:
                break
            time.sleep(2 * (attempt + 1))
        if not r.ok:
            print(f"[harvest] WARN {spelling}: {r.status_code}")
            continue
        for row in r.json().get("rows", []):
            rr = row["row"]
            rid = str(rr["id"])
            rows[rid] = {
                "id": rid,
                "name": rr.get("productDisplayName") or "",
                "colour": (rr.get("baseColour") or "").lower(),
                "season": (rr.get("season") or "").lower(),
                "usage": (rr.get("usage") or "").lower(),
                "gender": (rr.get("gender") or "").lower(),
                "img_src": rr["image"]["src"],
            }
    return list(rows.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--table", default="adidlabs-catalog")
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--per-brand", type=int, default=8)
    ap.add_argument("--candidates-per-brand", type=int, default=24)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", action="store_true", help="write rows to DynamoDB")
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    args = ap.parse_args()

    with open(args.catalog, encoding="utf-8") as fh:
        catalog = json.load(fh)
    existing_ids = {i["item_id"] for i in catalog}

    session = requests.Session()
    s3 = boto3.client("s3", region_name=args.region)
    new_items: list[dict] = []

    for brand, spellings in BRAND_SPELLINGS.items():
        cands = [c for c in harvest_brand(session, spellings,
                                          args.candidates_per_brand)
                 if f"kt-{c['id']}" not in existing_ids]
        print(f"[{brand}] {len(cands)} candidates")
        verified: list[dict] = []
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(process_candidate, c, args.region) for c in cands]
            for fut in as_completed(futs):
                row = fut.result()
                if row:
                    verified.append(row)

        # Round-robin over categories so one brand doesn't land 8 t-shirts.
        by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
        for r in sorted(verified, key=lambda r: r["id"]):
            by_cat[r["category"]].append(r)
        chosen: list[dict] = []
        while len(chosen) < args.per_brand and any(by_cat.values()):
            for cat in CATEGORIES:
                if by_cat[cat] and len(chosen) < args.per_brand:
                    chosen.append(by_cat[cat].pop(0))
        print(f"[{brand}] verified {len(verified)}, selected {len(chosen)}: "
              f"{[(r['category'], r['noun']) for r in chosen]}")

        for r in chosen:
            item_id = f"kt-{r['id']}"
            colour = r["vision_colour"] or r["colour"]
            s3.put_object(
                Bucket=args.bucket, Key=f"{IMG_PREFIX}/{item_id}.jpg",
                Body=r["hosted_bytes"], ContentType="image/jpeg",
                CacheControl="public,max-age=31536000,immutable",
            )
            new_items.append({
                "item_id": item_id,
                "category": r["category"],
                "name": synthesize_name_from_noun(item_id, r["category"],
                                                  colour, r["noun"]),
                "base_colour": colour,
                "season": r["season"] or "all-season",
                "usage": r["usage"] or "casual",
                "article_type": r["noun"].lower(),
                "gender": r["gender"],
                "brand": brand,
                "source": f"huggingface:{DATASET}",
                "image_url": f"/{IMG_PREFIX}/{item_id}.jpg",
                **synthesize_price(item_id, r["category"]),
            })

    catalog += new_items
    with open(args.catalog, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1)
    print(f"[out] +{len(new_items)} branded items -> {args.catalog} "
          f"(total {len(catalog)})")

    if args.seed and new_items:
        from decimal import Decimal
        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
        with table.batch_writer(overwrite_by_pkeys=["item_id"]) as batch:
            for item in new_items:
                batch.put_item(Item=json.loads(json.dumps(item), parse_float=Decimal))
        print(f"[seed] {len(new_items)} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

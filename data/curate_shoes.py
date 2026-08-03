"""One-off curation (Stefano, 2026-08-03):

* SHOES: drop every sandal; replace with sneakers from the original
  ashraq/fashion-product-images-small catalog (photos pulled at 384x512 via
  the benitomartin upscale mirror of the same Kaggle ids, as before).
* Drop the India team-merch rows (Cabin/Solace Blue Jerseys, Aurora Blue
  Cap, Aurora White Tee).
* Restore hf-19744 "Relay Green Jacket" (adidas track jacket — photo still
  hosted at catalog-img/hf-19744.jpg).

Usage: python data/curate_shoes.py --bucket <site-bucket> [--seed]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from category_map import synthesize_price  # noqa: E402
from hybrid_catalog import BRAND_TOKENS, _filter  # noqa: E402
from rebuild_catalog import (  # noqa: E402
    IMG_PREFIX, process_candidate, synthesize_name_from_noun,
)

MIRROR = "benitomartin/fashion-product-images-small-384x512"  # ashraq ids

REMOVE_NAMES = {"Aurora White Tee", "Aurora Blue Cap",
                "Cabin Blue Jersey", "Solace Blue Jersey"}

RELAY_JACKET = {
    "item_id": "hf-19744", "category": "jacket", "name": "Relay Green Jacket",
    "base_colour": "green", "season": "fall", "usage": "sports",
    "article_type": "track jacket", "gender": "men", "brand": "adidas",
    "source": "huggingface:ashraq/fashion-product-images-small",
    "image_url": "/catalog-img/hf-19744.jpg",
    **synthesize_price("hf-19744", "jacket"),
}

SNEAKER_NOUNS = ("sneaker", "runner", "trainer", "sports shoe", "sneakers")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--table", default="adidlabs-catalog")
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    args = ap.parse_args()

    with open(args.catalog, encoding="utf-8") as fh:
        cat = json.load(fh)

    def is_sandal(i):
        at = str(i.get("article_type", "")).lower()
        return i["category"] == "shoes" and ("sandal" in at or "flip flop" in at)

    removed = [i for i in cat if is_sandal(i) or i["name"] in REMOVE_NAMES]
    keep = [i for i in cat if i not in removed]
    need = sum(1 for i in removed if i["category"] == "shoes")
    print(f"[remove] {len(removed)} rows "
          f"({[i['name'] for i in removed]}); need {need} sneakers")

    existing = {i["item_id"] for i in keep}
    session = requests.Session()
    pool: dict[str, dict] = {}
    for art in ("Sports Shoes", "Casual Shoes"):
        rows = _filter(session, MIRROR, "train", f"\"articleType\"='{art}'", 40)
        for row in rows:
            rr = row["row"]
            rid = f"hf-{rr['id']}"
            if rid in existing or rid in pool or rid == "hf-19744":
                continue
            pool[rid] = {
                "id": str(rr["id"]), "item_id": rid, "pool": "hf",
                "name": rr.get("productDisplayName") or "",
                "colour": (rr.get("baseColour") or "").lower(),
                "season": (rr.get("season") or "").lower(),
                "usage": (rr.get("usage") or "").lower(),
                "gender": (rr.get("gender") or "").lower(),
                "img_src": rr["image"]["src"],
            }
    print(f"[harvest] {len(pool)} sneaker candidates")

    verified: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(process_candidate, c, args.region)
                for c in pool.values()]
        for fut in as_completed(futs):
            r = fut.result()
            if r and r["category"] == "shoes" and \
                    any(n in r["noun"].lower() for n in SNEAKER_NOUNS):
                verified.append(r)
    chosen = sorted(verified, key=lambda r: r["id"])[:need]
    print(f"[select] {len(chosen)}/{need} verified sneakers")

    s3 = boto3.client("s3", region_name=args.region)
    new_items: list[dict] = []
    for r in chosen:
        item_id = r["item_id"]
        colour = r["vision_colour"] or r["colour"]
        s3.put_object(Bucket=args.bucket, Key=f"{IMG_PREFIX}/{item_id}.jpg",
                      Body=r["hosted_bytes"], ContentType="image/jpeg",
                      CacheControl="public,max-age=31536000,immutable")
        brand = next((b for b in BRAND_TOKENS
                      if re.search(rf"\b{b}\b", r["name"].lower())), None)
        new_items.append({
            "item_id": item_id, "category": "shoes",
            "name": synthesize_name_from_noun(item_id, "shoes", colour, r["noun"]),
            "base_colour": colour, "season": r["season"] or "all-season",
            "usage": r["usage"] or "casual", "article_type": r["noun"].lower(),
            "gender": r["gender"],
            **({"brand": brand} if brand else {}),
            "source": "huggingface:ashraq/fashion-product-images-small",
            "image_url": f"/{IMG_PREFIX}/{item_id}.jpg",
            **synthesize_price(item_id, "shoes"),
        })

    final = keep + new_items + [RELAY_JACKET]
    with open(args.catalog, "w", encoding="utf-8") as fh:
        json.dump(final, fh, indent=1)
    print(f"[out] catalog now {len(final)} rows "
          f"(+{len(new_items)} sneakers, +Relay Green Jacket)")

    if args.seed:
        from decimal import Decimal
        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
        with table.batch_writer(overwrite_by_pkeys=["item_id"]) as batch:
            for item in new_items + [RELAY_JACKET]:
                batch.put_item(Item=json.loads(json.dumps(item), parse_float=Decimal))
        with table.batch_writer() as batch:
            for i in removed:
                batch.delete_item(Key={"item_id": i["item_id"]})
        print(f"[seed] +{len(new_items) + 1} rows, -{len(removed)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

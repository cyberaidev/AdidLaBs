"""Rebuild the AdidLaBs catalog from HuggingFace ktrinh38/fashion-dataset.

The dataset (44k Myntra products, full-res photos) carries NO articleType /
masterCategory columns — only displayCategories tags and the product name —
so naive keyword mapping miscategorizes. This pipeline:

  1. harvests candidates per category via datasets-server /filter on
     productDisplayName keywords,
  2. verifies EVERY candidate with Claude Haiku vision on Amazon Bedrock:
     the model sees the actual photo and returns the AdidLaBs category
     (or REJECT) plus a product noun used for the fictional name,
  3. selects a balanced set per category,
  4. rehosts each photo to the site bucket (catalog-img/kt-<id>.jpg),
  5. writes data/catalog.json (seed_dynamodb.py-compatible rows) and, with
     --seed, replaces the DynamoDB catalog (old hf-* rows deleted; their
     S3 photos are kept so previously persisted bag rows keep rendering).

Usage:
    python data/rebuild_catalog.py --bucket <site-bucket> [--seed \
        --table adidlabs-catalog] [--per-category 34] [--region ap-southeast-2]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from category_map import (  # noqa: E402
    _COLOUR_WORDS, _NAME_ADJECTIVES, _hash_int, synthesize_price,
)

DATASET = "ktrinh38/fashion-dataset"
FILTER_URL = "https://datasets-server.huggingface.co/filter"
MODEL_ID = "au.anthropic.claude-haiku-4-5-20251001-v1:0"
IMG_PREFIX = "catalog-img"

# productDisplayName keyword harvest per AdidLaBs category. The vision pass
# has final say — these only decide which rows are worth checking.
HARVEST: dict[str, list[str]] = {
    "shoes": ["Sports Shoes", "Casual Shoes", "Formal Shoes", "Sandals",
              "Flip Flops", "Sneakers", "Boots", "Heels", "Flats"],
    "pants": ["Jeans", "Track Pants", "Trousers", "Shorts", "Leggings"],
    "tshirt": ["T-shirt", "Tshirt", "Polo", "Shirt", "Top"],
    "jumper": ["Sweater", "Sweatshirt", "Pullover", "Hoodie", "Cardigan"],
    "jacket": ["Jacket", "Blazer", "Coat"],
    "accessory": ["Watch", "Belt", "Handbag", "Backpack", "Cap",
                  "Sunglasses", "Wallet", "Socks", "Scarf", "Duffel Bag"],
}

CATEGORIES = list(HARVEST.keys())

CLASSIFY_PROMPT = """You are categorizing products for a fashion storefront with EXACTLY six sections:
SHOES (all footwear), PANTS (jeans, trousers, track pants, shorts, leggings),
TSHIRT (t-shirts, polos, shirts, tops), JUMPER (sweaters, sweatshirts, hoodies,
cardigans), JACKET (jackets, blazers, coats), ACCESSORY (watches, belts, bags,
backpacks, caps, sunglasses, wallets, socks, scarves).

Product listing name: "{name}"

Look at the photo and answer for the PRODUCT BEING SOLD (the listing name tells
you which garment, if the photo shows a person wearing several).

Reply with ONLY a JSON object, no other text:
{{"category": "<SHOES|PANTS|TSHIRT|JUMPER|JACKET|ACCESSORY|REJECT>",
  "noun": "<one or two words naming the product type, e.g. Runner, Sneaker, Polo, Tee, Watch, Handbag, Hoodie, Blazer, Jean, Shorts>",
  "colour": "<single dominant colour word of the product, e.g. black>"}}

Use REJECT when: the product is underwear/innerwear, kidswear, jewellery,
beauty, or home goods; the photo is unclear; or the product does not fit any
of the six sections."""


def harvest_candidates(session: requests.Session, per_keyword: int) -> dict[str, dict]:
    """Return {id: row} candidate pool tagged with its harvest category."""
    pool: dict[str, dict] = {}
    for cat, keywords in HARVEST.items():
        for kw in keywords:
            params = {
                "dataset": DATASET, "config": "default", "split": "train",
                "where": f"\"productDisplayName\" LIKE '%{kw}%' AND \"ageGroup\" LIKE 'Adults%'",
                "limit": per_keyword,
            }
            for attempt in range(5):
                r = session.get(FILTER_URL, params=params, timeout=60)
                if r.ok:
                    break
                time.sleep(2 * (attempt + 1))
            if not r.ok:
                print(f"[harvest] WARN {cat}/{kw}: {r.status_code}")
                continue
            for row in r.json().get("rows", []):
                rr = row["row"]
                rid = str(rr["id"])
                if rid not in pool:
                    pool[rid] = {
                        "id": rid,
                        "name": rr.get("productDisplayName") or "",
                        "colour": (rr.get("baseColour") or "").lower(),
                        "season": (rr.get("season") or "").lower(),
                        "usage": (rr.get("usage") or "").lower(),
                        "gender": (rr.get("gender") or "").lower(),
                        "img_src": rr["image"]["src"],
                        "harvest_cat": cat,
                    }
        print(f"[harvest] {cat}: pool now {len(pool)}")
    return pool


def downscale(data: bytes, max_side: int) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82)
    return out.getvalue()


def classify(bedrock, image_bytes: bytes, name: str, tries: int = 4) -> dict | None:
    prompt = CLASSIFY_PROMPT.format(name=name.replace('"', "'"))
    for attempt in range(tries):
        try:
            r = bedrock.converse(
                modelId=MODEL_ID,
                messages=[{"role": "user", "content": [
                    {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
                    {"text": prompt},
                ]}],
                inferenceConfig={"maxTokens": 120, "temperature": 0},
            )
            text = r["output"]["message"]["content"][0]["text"].strip()
            start, end = text.find("{"), text.rfind("}")
            verdict = json.loads(text[start:end + 1])
            cat = str(verdict.get("category", "")).upper()
            if cat == "REJECT":
                return {"category": None}
            if cat.lower() in CATEGORIES or cat in [c.upper() for c in CATEGORIES]:
                return {
                    "category": cat.lower(),
                    "noun": str(verdict.get("noun") or "").strip().title()[:24],
                    "colour": str(verdict.get("colour") or "").strip().lower(),
                }
            return {"category": None}
        except Exception as exc:  # throttling / transient
            if attempt == tries - 1:
                print(f"[classify] FAILED {name[:40]}: {exc!r}")
                return None
            time.sleep(3 * (attempt + 1))
    return None


def synthesize_name_from_noun(item_id: str, category: str, colour: str, noun: str) -> str:
    h = _hash_int(f"name:{item_id}:{category}")
    adj = _NAME_ADJECTIVES[h % len(_NAME_ADJECTIVES)]
    colour_word = (colour or "").split()[0] if colour else ""
    colour_part = f" {colour_word.title()}" if colour_word in _COLOUR_WORDS else ""
    return f"{adj}{colour_part} {noun or 'Piece'}"


def process_candidate(cand: dict, region: str) -> dict | None:
    """Download + classify one candidate; returns enriched row or None."""
    boto = boto3.session.Session(region_name=region)
    bedrock = boto.client("bedrock-runtime")
    http = requests.Session()
    img = http.get(cand["img_src"], timeout=60)
    if not img.ok or not img.content:
        return None
    small = downscale(img.content, 512)
    verdict = classify(bedrock, small, cand["name"])
    if not verdict or not verdict.get("category"):
        return None
    return {
        **cand,
        "category": verdict["category"],
        "noun": verdict["noun"],
        "vision_colour": verdict["colour"],
        "hosted_bytes": downscale(img.content, 720),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--table", default="adidlabs-catalog")
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--per-category", type=int, default=34)
    ap.add_argument("--per-keyword", type=int, default=12)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", action="store_true",
                    help="replace the DynamoDB catalog (delete old rows)")
    ap.add_argument("--out", default=os.path.join(HERE, "catalog.json"))
    args = ap.parse_args()

    session = requests.Session()
    pool = harvest_candidates(session, args.per_keyword)
    print(f"[pool] {len(pool)} unique candidates")

    verified: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_candidate, c, args.region): c["id"]
                for c in pool.values()}
        for fut in as_completed(futs):
            done += 1
            row = fut.result()
            if row:
                verified[row["category"]].append(row)
            if done % 40 == 0:
                counts = {c: len(v) for c, v in verified.items()}
                print(f"[classify] {done}/{len(pool)} verified={counts}")

    counts = {c: len(v) for c, v in verified.items()}
    print(f"[classify] complete: {counts}")

    s3 = boto3.client("s3", region_name=args.region)
    items: list[dict] = []
    for cat in CATEGORIES:
        # Stable order for reproducibility; variety via colour spread.
        chosen = sorted(verified[cat], key=lambda r: r["id"])[: args.per_category]
        if len(chosen) < args.per_category:
            print(f"[select] WARN {cat}: only {len(chosen)} verified items")
        for r in chosen:
            item_id = f"kt-{r['id']}"
            colour = r["vision_colour"] or r["colour"]
            noun = r["noun"]
            s3.put_object(
                Bucket=args.bucket, Key=f"{IMG_PREFIX}/{item_id}.jpg",
                Body=r["hosted_bytes"], ContentType="image/jpeg",
                CacheControl="public,max-age=31536000,immutable",
            )
            items.append({
                "item_id": item_id,
                "category": cat,
                "name": synthesize_name_from_noun(item_id, cat, colour, noun),
                "base_colour": colour,
                "season": r["season"] or "all-season",
                "usage": r["usage"] or "casual",
                "article_type": noun.lower(),
                "gender": r["gender"],
                "source": f"huggingface:{DATASET}",
                "image_url": f"/{IMG_PREFIX}/{item_id}.jpg",
                **synthesize_price(item_id, cat),
            })
    print(f"[select] {len(items)} items rehosted + built")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1)
    print(f"[out] wrote {args.out}")

    if args.seed:
        ddb = boto3.resource("dynamodb", region_name=args.region)
        table = ddb.Table(args.table)
        old_ids, kwargs = [], {"ProjectionExpression": "item_id"}
        while True:
            page = table.scan(**kwargs)
            old_ids += [i["item_id"] for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        from decimal import Decimal
        with table.batch_writer(overwrite_by_pkeys=["item_id"]) as batch:
            for item in items:
                batch.put_item(Item=json.loads(json.dumps(item), parse_float=Decimal))
        new_ids = {i["item_id"] for i in items}
        stale = [i for i in old_ids if i not in new_ids]
        with table.batch_writer() as batch:
            for iid in stale:
                batch.delete_item(Key={"item_id": iid})
        print(f"[seed] {len(items)} rows written, {len(stale)} old rows deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())

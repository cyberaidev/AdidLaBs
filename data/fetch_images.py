"""Rehost catalog product photographs onto the site bucket.

For every ``hf-<id>`` row in the DynamoDB catalog, pull the matching product
photograph from the HuggingFace fashion dataset (384x512 upscale of the same
Kaggle corpus the catalog metadata came from), upload it to the static site
bucket under ``catalog-img/hf-<id>.jpg``, and stamp the row with a
site-relative ``image_url``.

Self-hosting matters: datasets-server asset URLs are signed and expire, and
third-party mirrors come and go. Serving from our own CloudFront keeps the
demo stable and adds zero idle cost (~200 images x ~20 KB).

Usage:
    python data/fetch_images.py --table adidlabs-catalog \
        --bucket <site-bucket> --region ap-southeast-2 [--force]
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

DATASET = "benitomartin/fashion-product-images-small-384x512"
FILTER_URL = "https://datasets-server.huggingface.co/filter"
IMG_PREFIX = "catalog-img"


def hf_image_src(raw_id: str, session: requests.Session, tries: int = 5) -> str | None:
    """Resolve a dataset product id to a (signed, short-lived) image URL."""
    params = {
        "dataset": DATASET,
        "config": "default",
        "split": "train",
        "where": f"\"id\"='{raw_id}'",
        "limit": 1,
    }
    for attempt in range(tries):
        resp = session.get(FILTER_URL, params=params, timeout=30)
        if resp.ok:
            rows = resp.json().get("rows", [])
            if not rows:
                return None  # id not present in the mirror
            return rows[0]["row"]["image"]["src"]
        # 429 / index-loading — back off and retry
        time.sleep(2 * (attempt + 1))
    return None


def process(item_id: str, bucket: str, region: str, force: bool) -> tuple[str, str]:
    # boto3 default sessions/resources are not thread-safe — build per-call
    # clients from a fresh Session (cheap next to the network work here).
    boto = boto3.session.Session(region_name=region)
    s3 = boto.client("s3")
    table = boto.resource("dynamodb").Table(process.table_name)
    http = requests.Session()

    raw_id = item_id[3:]
    key = f"{IMG_PREFIX}/{item_id}.jpg"
    rel_url = f"/{key}"

    if not force:
        try:
            s3.head_object(Bucket=bucket, Key=key)
            table.update_item(
                Key={"item_id": item_id},
                UpdateExpression="SET image_url = :u",
                ExpressionAttributeValues={":u": rel_url},
            )
            return item_id, "exists"
        except s3.exceptions.ClientError as err:
            code = err.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise  # AccessDenied/throttle etc. — surface, don't re-upload

    src = hf_image_src(raw_id, http)
    if not src:
        return item_id, "no-source"

    img = http.get(src, timeout=60)
    if not img.ok or not img.content:
        return item_id, f"download-{img.status_code}"

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=img.content,
        ContentType="image/jpeg",
        CacheControl="public,max-age=31536000,immutable",
    )
    table.update_item(
        Key={"item_id": item_id},
        UpdateExpression="SET image_url = :u",
        ExpressionAttributeValues={":u": rel_url},
    )
    return item_id, "uploaded"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="adidlabs-catalog")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--region", default="ap-southeast-2")
    ap.add_argument("--force", action="store_true",
                    help="re-download and re-upload even if the S3 object exists")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    process.table_name = args.table
    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)

    ids: list[str] = []
    scan_kwargs = {"ProjectionExpression": "item_id"}
    while True:
        page = table.scan(**scan_kwargs)
        ids += [r["item_id"] for r in page.get("Items", [])
                if str(r.get("item_id", "")).startswith("hf-")
                and str(r["item_id"])[3:].isdigit()]
        if "LastEvaluatedKey" not in page:
            break
        scan_kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    print(f"[images] {len(ids)} hf-* catalog rows")
    counts: dict[str, int] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process, i, args.bucket, args.region, args.force): i
                for i in ids}
        for n, fut in enumerate(as_completed(futs), 1):
            item_id, status = fut.result()
            counts[status] = counts.get(status, 0) + 1
            if status not in ("uploaded", "exists", "no-source"):
                failures.append(f"{item_id}: {status}")
            elif status == "no-source":
                # Not fatal: the SPA falls back to category photography.
                print(f"[images] WARN no dataset image for {item_id}")
            if n % 25 == 0 or n == len(ids):
                print(f"[images] {n}/{len(ids)} {counts}")

    for f in failures:
        print(f"[images] FAILED {f}")
    print(f"[images] done: {counts}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

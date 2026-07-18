#!/usr/bin/env python3
"""Seed the ``adidlabs-catalog`` DynamoDB table.

Reads the normalized catalog produced by :mod:`fetch_hf` (``data/catalog.json``;
generated on the fly if absent) and writes every item to the catalog table
(pk: ``item_id``) via ``batch_writer``. Idempotent: DynamoDB ``PutItem`` upserts,
so re-running overwrites in place rather than duplicating.

Region is pinned to ``ap-southeast-2`` (Sydney) per the contract. The table name
comes from ``CATALOG_TABLE`` (default ``adidlabs-catalog``). With
``--create-table`` the script will create the table on-demand
(``PAY_PER_REQUEST``) if it does not already exist.

Usage:
    python data/seed_dynamodb.py [--table adidlabs-catalog] [--region ap-southeast-2]
                                 [--catalog data/catalog.json] [--create-table]
                                 [--target 200] [--force-fallback]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fetch_hf import build_catalog

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CATALOG = os.path.join(HERE, "catalog.json")
DEFAULT_TABLE = os.environ.get("CATALOG_TABLE", "adidlabs-catalog")
DEFAULT_REGION = "ap-southeast-2"


def _to_dynamo(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert floats to Decimal (DynamoDB rejects native floats)."""
    out: Dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, float):
            out[key] = Decimal(str(value))
        elif isinstance(value, bool):
            out[key] = value
        else:
            out[key] = value
    return out


def load_or_build_catalog(path: str, target: int, force_fallback: bool) -> List[Dict[str, Any]]:
    """Load catalog.json if present, else build it (HF or fallback)."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return list(json.load(fh))
    items, source = build_catalog(target, force_fallback)
    print(f"[seed] built catalog on the fly (source={source}, {len(items)} items)")
    return items


def ensure_table(dynamodb, table_name: str):
    """Return the table resource, creating it (PAY_PER_REQUEST) if needed."""
    client = dynamodb.meta.client
    existing = client.list_tables().get("TableNames", [])
    if table_name not in existing:
        print(f"[seed] creating table {table_name} (PAY_PER_REQUEST)…")
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=[{"AttributeName": "item_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=table_name)
        print(f"[seed] table {table_name} is active.")
    return dynamodb.Table(table_name)


def seed(items: List[Dict[str, Any]], table_name: str, region: str,
         create_table: bool) -> int:
    """Write all items to the table. Returns count written."""
    try:
        import boto3  # type: ignore
    except ImportError:
        print("[seed] ERROR: boto3 is required to seed DynamoDB. "
              "Install with `pip install boto3`.", file=sys.stderr)
        return 0

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = ensure_table(dynamodb, table_name) if create_table else dynamodb.Table(table_name)

    written = 0
    with table.batch_writer(overwrite_by_pkeys=["item_id"]) as batch:
        for item in items:
            batch.put_item(Item=_to_dynamo(item))
            written += 1
    return written


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed adidlabs-catalog DynamoDB table.")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="Table name.")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region.")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Catalog JSON path.")
    parser.add_argument("--create-table", action="store_true",
                        help="Create the table (PAY_PER_REQUEST) if it does not exist.")
    parser.add_argument("--target", type=int, default=200,
                        help="Items to sample if catalog.json is built on the fly.")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Use synthetic_fallback.json instead of HF.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load/validate the catalog but do not write to DynamoDB.")
    args = parser.parse_args(argv)

    items = load_or_build_catalog(args.catalog, args.target, args.force_fallback)
    if not items:
        print("[seed] ERROR: no items to seed.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[seed] dry-run: {len(items)} items would be written to "
              f"{args.table} ({args.region}).")
        return 0

    written = seed(items, args.table, args.region, args.create_table)
    if written == 0:
        return 1
    print(f"[seed] wrote {written} items to {args.table} ({args.region}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

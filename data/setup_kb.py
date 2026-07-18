#!/usr/bin/env python3
"""Create the AdidLaBs Bedrock Knowledge Base over Amazon S3 Vectors (boto3).

Why boto3 and not CloudFormation: S3 Vectors + the KB S3-Vectors integration
are preview/newly-GA and not a stable CFN resource type; provisioning them
outside a stack means a preview-service hiccup can't roll back the durable CFN
stack. This script is **idempotent** (safe to re-run) and supports clean
``--teardown``.

Pipeline built here (all in ap-southeast-2):
  1. S3 **corpus** bucket  — holds the markdown KB docs (data/kb_docs/). Created
     private and self-enforcing: Block Public Access (all four flags) + default
     SSE-S3 encryption, so the "private corpus bucket" posture in docs/SECURITY.md
     never relies on account defaults.
  2. Upload the generated docs to the corpus bucket.
  3. S3 **Vectors** bucket + vector **index** (dim 1024 for Titan Text v2,
     cosine distance) via the ``s3vectors`` client.
  4. Bedrock **Knowledge Base** with an S3-Vectors storage configuration and an
     S3 **data source** pointing at the corpus bucket.
  5. **Ingestion job** (start + poll) to embed + index the corpus.
  6. Print ``KB_ID`` to stdout (the last stdout line is exactly the id, so
     ``KB_ID=$(python data/setup_kb.py ... | tail -n1)`` works).

Idempotency strategy: every resource is looked up by a deterministic name/tag
before creation; if it already exists we reuse it. Re-running converges to the
same state and re-triggers ingestion.

Requires an IAM role ARN the KB assumes (``--kb-role-arn`` or ``KB_ROLE_ARN``)
with Bedrock KB + S3 + S3 Vectors + Titan invoke permissions (see data/README).

Usage:
    python data/setup_kb.py --kb-role-arn arn:aws:iam::<acct>:role/AdidLabsKBRole
    python data/setup_kb.py --teardown
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOCS_DIR = os.path.join(HERE, "kb_docs")

REGION = "ap-southeast-2"

# Deterministic resource names (idempotent lookups key off these).
KB_NAME = "adidlabs-knowledge-base"
DATA_SOURCE_NAME = "adidlabs-kb-datasource"   # distinct from the S3 bucket name below (different namespace)
CORPUS_BUCKET = "adidlabs-kb-corpus"          # + account suffix appended at runtime
VECTOR_BUCKET = "adidlabs-kb-vectors"         # + account suffix appended at runtime
VECTOR_INDEX = "adidlabs-kb-index"
CORPUS_PREFIX = "corpus/"

# Titan Text Embeddings v2 -> 1024 dims, cosine. Contract embedding model.
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024
DISTANCE_METRIC = "cosine"

# Bedrock KB writes these metadata keys; they must be non-filterable on S3 Vectors.
NON_FILTERABLE_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]


# --------------------------------------------------------------------------- #
# boto3 client helpers
# --------------------------------------------------------------------------- #
def _clients(region: str) -> Dict[str, Any]:
    import boto3  # type: ignore

    sts = boto3.client("sts", region_name=region)
    account = sts.get_caller_identity()["Account"]
    return {
        "account": account,
        "s3": boto3.client("s3", region_name=region),
        "s3vectors": boto3.client("s3vectors", region_name=region),
        "bedrock_agent": boto3.client("bedrock-agent", region_name=region),
    }


def _names(account: str) -> Dict[str, str]:
    """Account-suffixed globally-unique bucket names."""
    return {
        "corpus_bucket": f"{CORPUS_BUCKET}-{account}",
        "vector_bucket": f"{VECTOR_BUCKET}-{account}",
    }


def _model_arn(region: str, account: str) -> str:
    # Foundation-model ARN form used by KB embedding configuration.
    return f"arn:aws:bedrock:{region}::foundation-model/{EMBED_MODEL_ID}"


def _vector_bucket_arn(region: str, account: str, name: str) -> str:
    return f"arn:aws:s3vectors:{region}:{account}:bucket/{name}"


def _index_arn(region: str, account: str, bucket: str, index: str) -> str:
    return f"arn:aws:s3vectors:{region}:{account}:bucket/{bucket}/index/{index}"


# --------------------------------------------------------------------------- #
# Step 1/2 — corpus S3 bucket + upload docs
# --------------------------------------------------------------------------- #
def _harden_corpus_bucket(s3, bucket: str) -> None:
    """Enforce the private posture docs/SECURITY.md promises for the corpus bucket.

    Two least-privilege controls, both self-enforcing so we never rely on the
    account's default settings:
      1. **Block Public Access** — all four flags ``True`` (no public ACLs, no
         public policy, ignore any stray public ACLs, restrict cross-account
         public policy). Makes the "no public bucket, no ACLs" claim real.
      2. **Default encryption** — SSE-S3 (``AES256``) with S3 Bucket Keys so
         the KB markdown corpus is encrypted at rest by default.

    Applied on both the create path and the already-exists path, so re-running
    setup converges an older/looser bucket to the hardened posture (idempotent).
    """
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
                    "BucketKeyEnabled": True,
                }
            ]
        },
    )
    print(f"[kb] hardened corpus bucket {bucket}: block-public-access + SSE-S3")


def ensure_corpus_bucket(s3, bucket: str, region: str) -> None:
    from botocore.exceptions import ClientError  # type: ignore

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"[kb] corpus bucket exists: {bucket}")
        # Re-assert the private posture on rerun (idempotent, converges drift).
        _harden_corpus_bucket(s3, bucket)
        return
    except ClientError:
        pass
    print(f"[kb] creating corpus bucket: {bucket}")
    s3.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": region},
    )
    s3.get_waiter("bucket_exists").wait(Bucket=bucket)
    # A private bucket the module owns: never public, encrypted at rest.
    _harden_corpus_bucket(s3, bucket)


def upload_docs(s3, bucket: str, docs_dir: str) -> int:
    if not os.path.isdir(docs_dir):
        raise FileNotFoundError(
            f"KB docs dir not found: {docs_dir}. Run gen_kb_docs.py first."
        )
    count = 0
    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith(".md"):
            continue
        key = f"{CORPUS_PREFIX}{fname}"
        s3.upload_file(os.path.join(docs_dir, fname), bucket, key)
        count += 1
    print(f"[kb] uploaded {count} docs to s3://{bucket}/{CORPUS_PREFIX}")
    return count


# --------------------------------------------------------------------------- #
# Step 3 — S3 Vectors bucket + index (idempotent)
# --------------------------------------------------------------------------- #
def ensure_vector_bucket(s3vectors, bucket: str) -> None:
    from botocore.exceptions import ClientError  # type: ignore

    try:
        s3vectors.get_vector_bucket(vectorBucketName=bucket)
        print(f"[kb] vector bucket exists: {bucket}")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("NotFoundException", "ResourceNotFoundException"):
            raise
    print(f"[kb] creating vector bucket: {bucket}")
    s3vectors.create_vector_bucket(vectorBucketName=bucket)


def ensure_vector_index(s3vectors, bucket: str, index: str) -> None:
    from botocore.exceptions import ClientError  # type: ignore

    try:
        s3vectors.get_index(vectorBucketName=bucket, indexName=index)
        print(f"[kb] vector index exists: {index}")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("NotFoundException", "ResourceNotFoundException"):
            raise
    print(f"[kb] creating vector index: {index} (dim={EMBED_DIM}, {DISTANCE_METRIC})")
    s3vectors.create_index(
        vectorBucketName=bucket,
        indexName=index,
        dataType="float32",
        dimension=EMBED_DIM,
        distanceMetric=DISTANCE_METRIC,
        metadataConfiguration={"nonFilterableMetadataKeys": NON_FILTERABLE_KEYS},
    )


# --------------------------------------------------------------------------- #
# Step 4 — Bedrock Knowledge Base + data source (idempotent by name)
# --------------------------------------------------------------------------- #
def find_kb_by_name(bedrock_agent, name: str) -> Optional[str]:
    paginator = bedrock_agent.get_paginator("list_knowledge_bases")
    for page in paginator.paginate():
        for summary in page.get("knowledgeBaseSummaries", []):
            if summary.get("name") == name:
                return summary["knowledgeBaseId"]
    return None


def ensure_knowledge_base(bedrock_agent, region: str, account: str,
                          kb_role_arn: str, vector_bucket: str) -> str:
    existing = find_kb_by_name(bedrock_agent, KB_NAME)
    if existing:
        print(f"[kb] knowledge base exists: {existing}")
        return existing

    print(f"[kb] creating knowledge base: {KB_NAME}")
    resp = bedrock_agent.create_knowledge_base(
        name=KB_NAME,
        description="AdidLaBs lab corpus: weather-to-outfit guide, fabric care, "
                    "sizing/returns FAQ, product stories. Concept demo.",
        roleArn=kb_role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": _model_arn(region, account),
                "embeddingModelConfiguration": {
                    "bedrockEmbeddingModelConfiguration": {
                        "dimensions": EMBED_DIM,
                        "embeddingDataType": "FLOAT32",
                    }
                },
            },
        },
        storageConfiguration={
            "type": "S3_VECTORS",
            "s3VectorsConfiguration": {
                "vectorBucketArn": _vector_bucket_arn(region, account, vector_bucket),
                "indexArn": _index_arn(region, account, vector_bucket, VECTOR_INDEX),
            },
        },
    )
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    _wait_kb_active(bedrock_agent, kb_id)
    return kb_id


def _wait_kb_active(bedrock_agent, kb_id: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = bedrock_agent.get_knowledge_base(
            knowledgeBaseId=kb_id
        )["knowledgeBase"]["status"]
        if status == "ACTIVE":
            return
        if status in ("FAILED", "DELETE_UNSUCCESSFUL"):
            raise RuntimeError(f"KB {kb_id} entered status {status}")
        time.sleep(5)
    raise TimeoutError(f"KB {kb_id} did not become ACTIVE within {timeout}s")


def find_data_source(bedrock_agent, kb_id: str, name: str) -> Optional[str]:
    resp = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)
    for summary in resp.get("dataSourceSummaries", []):
        if summary.get("name") == name:
            return summary["dataSourceId"]
    return None


def ensure_data_source(bedrock_agent, kb_id: str, account: str,
                       corpus_bucket: str) -> str:
    existing = find_data_source(bedrock_agent, kb_id, DATA_SOURCE_NAME)
    if existing:
        print(f"[kb] data source exists: {existing}")
        return existing
    print(f"[kb] creating data source: {DATA_SOURCE_NAME}")
    resp = bedrock_agent.create_data_source(
        knowledgeBaseId=kb_id,
        name=DATA_SOURCE_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{corpus_bucket}",
                "inclusionPrefixes": [CORPUS_PREFIX],
            },
        },
    )
    return resp["dataSource"]["dataSourceId"]


# --------------------------------------------------------------------------- #
# Step 5 — ingestion
# --------------------------------------------------------------------------- #
def start_ingestion(bedrock_agent, kb_id: str, ds_id: str, wait: bool = True) -> str:
    resp = bedrock_agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = resp["ingestionJob"]["ingestionJobId"]
    print(f"[kb] started ingestion job: {job_id}")
    if not wait:
        return job_id
    deadline = time.time() + 600
    while time.time() < deadline:
        job = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )["ingestionJob"]
        status = job["status"]
        if status == "COMPLETE":
            stats = job.get("statistics", {})
            print(f"[kb] ingestion COMPLETE: {stats}")
            return job_id
        if status == "FAILED":
            reasons = job.get("failureReasons", [])
            raise RuntimeError(f"Ingestion failed: {reasons}")
        time.sleep(10)
    raise TimeoutError("Ingestion did not complete within 600s")


# --------------------------------------------------------------------------- #
# Teardown (reverse order)
# --------------------------------------------------------------------------- #
def teardown(clients: Dict[str, Any], region: str, docs_dir: str) -> None:
    from botocore.exceptions import ClientError  # type: ignore

    account = clients["account"]
    names = _names(account)
    s3 = clients["s3"]
    s3vectors = clients["s3vectors"]
    bedrock_agent = clients["bedrock_agent"]

    # 1. KB (and its data sources cascade on delete).
    kb_id = find_kb_by_name(bedrock_agent, KB_NAME)
    if kb_id:
        # delete data sources first (defensive; some APIs require it)
        try:
            for summary in bedrock_agent.list_data_sources(
                knowledgeBaseId=kb_id
            ).get("dataSourceSummaries", []):
                bedrock_agent.delete_data_source(
                    knowledgeBaseId=kb_id, dataSourceId=summary["dataSourceId"]
                )
                print(f"[kb][teardown] deleted data source {summary['dataSourceId']}")
        except ClientError as exc:
            print(f"[kb][teardown] data source delete note: {exc}", file=sys.stderr)
        bedrock_agent.delete_knowledge_base(knowledgeBaseId=kb_id)
        print(f"[kb][teardown] deleted knowledge base {kb_id}")
    else:
        print("[kb][teardown] no knowledge base to delete")

    # 2. Vector index then vector bucket.
    try:
        s3vectors.delete_index(vectorBucketName=names["vector_bucket"], indexName=VECTOR_INDEX)
        print(f"[kb][teardown] deleted vector index {VECTOR_INDEX}")
    except ClientError as exc:
        print(f"[kb][teardown] vector index note: {exc}", file=sys.stderr)
    try:
        s3vectors.delete_vector_bucket(vectorBucketName=names["vector_bucket"])
        print(f"[kb][teardown] deleted vector bucket {names['vector_bucket']}")
    except ClientError as exc:
        print(f"[kb][teardown] vector bucket note: {exc}", file=sys.stderr)

    # 3. Empty + delete corpus bucket.
    corpus = names["corpus_bucket"]
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=corpus):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=corpus, Delete={"Objects": objs})
        s3.delete_bucket(Bucket=corpus)
        print(f"[kb][teardown] deleted corpus bucket {corpus}")
    except ClientError as exc:
        print(f"[kb][teardown] corpus bucket note: {exc}", file=sys.stderr)

    print("[kb][teardown] done.")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def setup(clients: Dict[str, Any], region: str, kb_role_arn: str,
          docs_dir: str, skip_ingest: bool) -> str:
    account = clients["account"]
    names = _names(account)
    s3 = clients["s3"]
    s3vectors = clients["s3vectors"]
    bedrock_agent = clients["bedrock_agent"]

    ensure_corpus_bucket(s3, names["corpus_bucket"], region)
    upload_docs(s3, names["corpus_bucket"], docs_dir)

    ensure_vector_bucket(s3vectors, names["vector_bucket"])
    ensure_vector_index(s3vectors, names["vector_bucket"], VECTOR_INDEX)

    kb_id = ensure_knowledge_base(
        bedrock_agent, region, account, kb_role_arn, names["vector_bucket"]
    )
    ds_id = ensure_data_source(bedrock_agent, kb_id, account, names["corpus_bucket"])

    if not skip_ingest:
        start_ingestion(bedrock_agent, kb_id, ds_id, wait=True)

    return kb_id


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AdidLaBs S3-Vectors Knowledge Base setup.")
    parser.add_argument("--kb-role-arn", default=os.environ.get("KB_ROLE_ARN"),
                        help="IAM role ARN the KB assumes (or set KB_ROLE_ARN).")
    parser.add_argument("--region", default=REGION, help="AWS region (default ap-southeast-2).")
    parser.add_argument("--docs-dir", default=DEFAULT_DOCS_DIR, help="KB markdown docs dir.")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="Create resources but do not run the ingestion job.")
    parser.add_argument("--teardown", action="store_true",
                        help="Delete the KB, vector index/bucket, and corpus bucket.")
    args = parser.parse_args(argv)

    try:
        import boto3  # noqa: F401
        import botocore  # noqa: F401
    except ImportError:
        print("[kb] ERROR: boto3 is required (pip install boto3).", file=sys.stderr)
        return 2

    clients = _clients(args.region)

    if args.teardown:
        teardown(clients, args.region, args.docs_dir)
        return 0

    if not args.kb_role_arn:
        print("[kb] ERROR: --kb-role-arn (or KB_ROLE_ARN) is required for setup.",
              file=sys.stderr)
        return 2

    kb_id = setup(clients, args.region, args.kb_role_arn, args.docs_dir, args.skip_ingest)
    print(f"[kb] KB_ID={kb_id}")
    # Final stdout line is the bare id so callers can `| tail -n1`.
    print(kb_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

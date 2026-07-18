"""Idempotency + teardown tests for setup_kb.py using fake boto3 clients.

These prove the *control flow* of setup_kb.py without touching AWS:
  - a first `setup` creates every resource exactly once,
  - a second `setup` (rerun) creates nothing new (all lookups hit) and returns
    the same KB_ID,
  - `teardown` deletes the KB, vector index, vector bucket, and corpus bucket.

We inject fake clients that model create/get/list/delete with in-memory state.

Run:
    python -m pytest data/tests/test_setup_kb_idempotent.py -q
or directly:
    python data/tests/test_setup_kb_idempotent.py
"""

from __future__ import annotations

import os
import sys

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DATA_DIR not in sys.path:
    sys.path.insert(0, DATA_DIR)

import setup_kb  # noqa: E402


# --------------------------------------------------------------------------- #
# A minimal ClientError-compatible exception + fakes.
# --------------------------------------------------------------------------- #
class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


# Patch the botocore import inside setup_kb helpers to use our fake error.
class _FakeExceptionsModule:
    ClientError = FakeClientError


class FakeS3:
    def __init__(self, counters):
        self.counters = counters
        self.buckets = set()
        self.objects = {}
        self.public_access_block = {}
        self.encryption = {}

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise FakeClientError("404")

    def create_bucket(self, Bucket, CreateBucketConfiguration=None):
        self.counters["create_bucket"] += 1
        self.buckets.add(Bucket)

    def put_public_access_block(self, Bucket, PublicAccessBlockConfiguration):
        self.counters["put_public_access_block"] += 1
        # Record the enforced posture so the test can assert all four flags.
        self.public_access_block[Bucket] = PublicAccessBlockConfiguration

    def put_bucket_encryption(self, Bucket, ServerSideEncryptionConfiguration):
        self.counters["put_bucket_encryption"] += 1
        self.encryption[Bucket] = ServerSideEncryptionConfiguration

    def get_waiter(self, name):
        return _NoopWaiter()

    def upload_file(self, path, bucket, key):
        self.counters["upload_file"] += 1
        self.objects.setdefault(bucket, {})[key] = path

    def get_paginator(self, name):
        objs = self.objects
        buckets = self.buckets

        class _P:
            def paginate(self, Bucket):
                contents = [{"Key": k} for k in objs.get(Bucket, {})]
                yield {"Contents": contents}

        return _P()

    def delete_objects(self, Bucket, Delete):
        for o in Delete["Objects"]:
            self.objects.get(Bucket, {}).pop(o["Key"], None)

    def delete_bucket(self, Bucket):
        self.counters["delete_bucket"] += 1
        self.buckets.discard(Bucket)


class FakeS3Vectors:
    def __init__(self, counters):
        self.counters = counters
        self.vbuckets = set()
        self.indexes = set()

    def get_vector_bucket(self, vectorBucketName):
        if vectorBucketName not in self.vbuckets:
            raise FakeClientError("NotFoundException")
        return {"vectorBucket": {"vectorBucketName": vectorBucketName}}

    def create_vector_bucket(self, vectorBucketName):
        self.counters["create_vector_bucket"] += 1
        self.vbuckets.add(vectorBucketName)

    def get_index(self, vectorBucketName, indexName):
        if (vectorBucketName, indexName) not in self.indexes:
            raise FakeClientError("NotFoundException")
        return {"index": {"indexName": indexName}}

    def create_index(self, vectorBucketName, indexName, **kwargs):
        self.counters["create_index"] += 1
        self.indexes.add((vectorBucketName, indexName))

    def delete_index(self, vectorBucketName, indexName):
        self.counters["delete_index"] += 1
        self.indexes.discard((vectorBucketName, indexName))

    def delete_vector_bucket(self, vectorBucketName):
        self.counters["delete_vector_bucket"] += 1
        self.vbuckets.discard(vectorBucketName)


class _NoopWaiter:
    def wait(self, **kwargs):
        return None


class FakeBedrockAgent:
    def __init__(self, counters):
        self.counters = counters
        self.kbs = {}          # kb_id -> {"name":..., "status":"ACTIVE"}
        self.data_sources = {}  # kb_id -> {ds_id: name}
        self._kb_seq = 0
        self._ds_seq = 0

    # --- KB ---
    def get_paginator(self, name):
        kbs = self.kbs

        class _P:
            def paginate(self):
                yield {"knowledgeBaseSummaries": [
                    {"knowledgeBaseId": kid, "name": v["name"]}
                    for kid, v in kbs.items()
                ]}

        return _P()

    def create_knowledge_base(self, **kwargs):
        self.counters["create_knowledge_base"] += 1
        self._kb_seq += 1
        kb_id = f"KB{self._kb_seq:04d}"
        self.kbs[kb_id] = {"name": kwargs["name"], "status": "ACTIVE"}
        return {"knowledgeBase": {"knowledgeBaseId": kb_id, "status": "ACTIVE"}}

    def get_knowledge_base(self, knowledgeBaseId):
        return {"knowledgeBase": {"status": self.kbs[knowledgeBaseId]["status"]}}

    def delete_knowledge_base(self, knowledgeBaseId):
        self.counters["delete_knowledge_base"] += 1
        self.kbs.pop(knowledgeBaseId, None)
        self.data_sources.pop(knowledgeBaseId, None)

    # --- data sources ---
    def list_data_sources(self, knowledgeBaseId):
        return {"dataSourceSummaries": [
            {"dataSourceId": did, "name": nm}
            for did, nm in self.data_sources.get(knowledgeBaseId, {}).items()
        ]}

    def create_data_source(self, **kwargs):
        self.counters["create_data_source"] += 1
        self._ds_seq += 1
        ds_id = f"DS{self._ds_seq:04d}"
        self.data_sources.setdefault(kwargs["knowledgeBaseId"], {})[ds_id] = kwargs["name"]
        return {"dataSource": {"dataSourceId": ds_id}}

    def delete_data_source(self, knowledgeBaseId, dataSourceId):
        self.counters["delete_data_source"] += 1
        self.data_sources.get(knowledgeBaseId, {}).pop(dataSourceId, None)

    # --- ingestion ---
    def start_ingestion_job(self, knowledgeBaseId, dataSourceId):
        self.counters["start_ingestion_job"] += 1
        return {"ingestionJob": {"ingestionJobId": "JOB0001"}}

    def get_ingestion_job(self, knowledgeBaseId, dataSourceId, ingestionJobId):
        return {"ingestionJob": {"status": "COMPLETE", "statistics": {"docs": 4}}}


def _make_clients(counters):
    return {
        "account": "123456789012",
        "s3": FakeS3(counters),
        "s3vectors": FakeS3Vectors(counters),
        "bedrock_agent": FakeBedrockAgent(counters),
    }


def _patch_botocore(monkeypatch=None):
    """Point setup_kb's `from botocore.exceptions import ClientError` at our fake."""
    fake_mod = type(sys)("botocore")
    fake_exc = type(sys)("botocore.exceptions")
    fake_exc.ClientError = FakeClientError
    fake_mod.exceptions = fake_exc
    sys.modules["botocore"] = fake_mod
    sys.modules["botocore.exceptions"] = fake_exc


def _docs_dir():
    # Point at the real generated docs dir if present, else create a temp one.
    docs = os.path.join(DATA_DIR, "kb_docs")
    if os.path.isdir(docs) and any(f.endswith(".md") for f in os.listdir(docs)):
        return docs
    tmp = os.path.join(DATA_DIR, "tests", "_tmp_docs")
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "sample.md"), "w", encoding="utf-8") as fh:
        fh.write("# sample\n")
    return tmp


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_setup_is_idempotent_on_rerun():
    _patch_botocore()
    counters = _Counters()
    clients = _make_clients(counters)
    docs = _docs_dir()

    kb1 = setup_kb.setup(clients, setup_kb.REGION,
                         "arn:aws:iam::123456789012:role/KB", docs, skip_ingest=False)
    # First run creates each resource once.
    assert counters["create_bucket"] == 1
    assert counters["create_vector_bucket"] == 1
    assert counters["create_index"] == 1
    assert counters["create_knowledge_base"] == 1
    assert counters["create_data_source"] == 1
    assert counters["start_ingestion_job"] == 1

    # Second run: same clients (state persists) => nothing new created.
    kb2 = setup_kb.setup(clients, setup_kb.REGION,
                         "arn:aws:iam::123456789012:role/KB", docs, skip_ingest=False)
    assert kb1 == kb2, "rerun must return the same KB_ID"
    assert counters["create_bucket"] == 1
    assert counters["create_vector_bucket"] == 1
    assert counters["create_index"] == 1
    assert counters["create_knowledge_base"] == 1, "KB must not be recreated on rerun"
    assert counters["create_data_source"] == 1, "data source must not be recreated"
    # Ingestion is expected to re-run on rerun (refresh corpus).
    assert counters["start_ingestion_job"] == 2


def test_corpus_bucket_is_hardened_private():
    """setup_kb enforces Block Public Access (4 flags) + SSE-S3 on the corpus bucket.

    Guards the docs/SECURITY.md promise that "the KB corpus bucket is likewise
    private" — the code, not the account default, must make it so.
    """
    _patch_botocore()
    counters = _Counters()
    clients = _make_clients(counters)
    s3 = clients["s3"]
    docs = _docs_dir()

    setup_kb.setup(clients, setup_kb.REGION,
                   "arn:aws:iam::123456789012:role/KB", docs, skip_ingest=True)

    corpus = setup_kb._names(clients["account"])["corpus_bucket"]

    # Block Public Access — all four flags must be True.
    bpa = s3.public_access_block[corpus]
    assert bpa == {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }, f"corpus bucket public-access-block not fully locked down: {bpa}"

    # Default encryption — SSE-S3 (AES256).
    rules = s3.encryption[corpus]["Rules"]
    algo = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
    assert algo == "AES256", f"corpus bucket not SSE-S3 encrypted by default: {algo}"

    # Hardening was applied on first run (create path).
    assert counters["put_public_access_block"] == 1
    assert counters["put_bucket_encryption"] == 1

    # Rerun re-asserts the posture (idempotent, converges drift) without
    # recreating the bucket.
    setup_kb.setup(clients, setup_kb.REGION,
                   "arn:aws:iam::123456789012:role/KB", docs, skip_ingest=True)
    assert counters["create_bucket"] == 1, "bucket must not be recreated on rerun"
    assert counters["put_public_access_block"] == 2, "posture must be re-asserted on rerun"
    assert counters["put_bucket_encryption"] == 2, "encryption must be re-asserted on rerun"


def test_teardown_deletes_everything():
    _patch_botocore()
    counters = _Counters()
    clients = _make_clients(counters)
    docs = _docs_dir()

    setup_kb.setup(clients, setup_kb.REGION,
                   "arn:aws:iam::123456789012:role/KB", docs, skip_ingest=True)
    setup_kb.teardown(clients, setup_kb.REGION, docs)

    assert counters["delete_knowledge_base"] == 1
    assert counters["delete_data_source"] == 1
    assert counters["delete_index"] == 1
    assert counters["delete_vector_bucket"] == 1
    assert counters["delete_bucket"] == 1
    # State fully drained.
    assert clients["bedrock_agent"].kbs == {}
    assert clients["s3vectors"].vbuckets == set()
    assert clients["s3vectors"].indexes == set()


def test_teardown_is_safe_when_nothing_exists():
    _patch_botocore()
    counters = _Counters()
    clients = _make_clients(counters)
    # Teardown on empty state should not raise.
    setup_kb.teardown(clients, setup_kb.REGION, _docs_dir())
    assert counters["delete_knowledge_base"] == 0


class _Counters(dict):
    """dict that defaults missing keys to 0 so `+= 1` always works."""
    def __missing__(self, key):
        self[key] = 0
        return 0


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

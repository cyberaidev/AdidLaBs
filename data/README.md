# AdidLaBs — `data/` module

> **Concept demo - no affiliation with adidas AG. All products fictional.**

This module produces everything downstream tests against: the **catalog seed**
for the `adidlabs-catalog` DynamoDB table and the **Knowledge Base corpus** for
the Bedrock KB over Amazon S3 Vectors. Region is **`ap-southeast-2` (Sydney)**.

Build order (per the coordinator work order): produce the catalog seed and the
KB corpus **first** — the agents, MCP tools, and API handler all depend on them.

---

## Contents

| File | What it does |
|---|---|
| `category_map.py` | Stdlib-only mapping of HF metadata rows → the six contract categories, plus deterministic EUR price/deal synthesis and **brand-safe fictional name** synthesis. No deps. |
| `fetch_hf.py` | Pulls ~200 metadata rows from HuggingFace `ashraq/fashion-product-images-small` via the **datasets-server rows REST API** (`requests` only — never the `datasets` library). Paginates politely with timeouts and enforces a **per-category minimum count** (`MIN_PER_CATEGORY`, default 6) — not just presence — paging deeper to fill the sparse `jumper`/`jacket` buckets, then trimming back toward the target without dropping any category below its floor. On **any** failure, missing category, or an unreachable floor, falls back to `synthetic_fallback.json`. Writes `catalog.json`. |
| `synthetic_fallback.json` | ~40 handwritten, fully fictional items covering all six categories. Used when HF is unreachable. |
| `seed_dynamodb.py` | Loads `catalog.json` into `adidlabs-catalog` (pk `item_id`) via `batch_writer` (idempotent upserts). Optional `--create-table` (PAY_PER_REQUEST). |
| `gen_kb_docs.py` | Generates the KB markdown corpus into `kb_docs/`: weather-to-outfit style guide, fabric care sheets, sizing/returns FAQ, and product stories grounded on the real catalog `item_id`s. |
| `setup_kb.py` | **boto3** creation of the S3 corpus bucket, S3 **Vectors** bucket + index, Bedrock **Knowledge Base** + S3 data source, and the ingestion job. **Idempotent**; prints `KB_ID`; `--teardown` removes everything. Not CloudFormation (see below). |
| `tests/` | Unit tests for the category mapping (fixture covers all six) and price synthesis; the per-category **floor** logic in `fetch_hf` (`test_fetch_hf_floor.py`); and provable idempotency/teardown **plus corpus-bucket hardening** tests for `setup_kb.py` (fake boto3 clients, no AWS needed). |
| `requirements.txt` | `requests` (fetch) + `boto3` (seed/KB). |

---

## Quick start

```bash
pip install -r data/requirements.txt

# 1. Fetch the catalog (HF → catalog.json; auto-falls back to synthetic on failure)
python data/fetch_hf.py --target 200            # writes data/catalog.json
#    force the offline path for a hermetic build:
python data/fetch_hf.py --force-fallback

# 2. Seed DynamoDB (ap-southeast-2). --create-table makes it if absent.
python data/seed_dynamodb.py --create-table

# 3. Generate the KB markdown corpus
python data/gen_kb_docs.py                       # writes data/kb_docs/*.md

# 4. Build the S3-Vectors Knowledge Base (needs an IAM role the KB assumes)
export KB_ROLE_ARN=arn:aws:iam::<acct>:role/AdidLabsKBRole
KB_ID=$(python data/setup_kb.py | tail -n1)      # last stdout line is the bare id
echo "KB_ID=$KB_ID"

# Teardown (preview KB was made outside CloudFormation)
python data/setup_kb.py --teardown
```

Run the tests:

```bash
python -m pytest data/tests/ -q
# or, with no pytest installed:
python data/tests/test_category_map.py
python data/tests/test_setup_kb_idempotent.py
```

---

## Dataset attribution & license note

Mock data is sampled from the HuggingFace dataset
**[`ashraq/fashion-product-images-small`](https://huggingface.co/datasets/ashraq/fashion-product-images-small)**,
which repackages the Kaggle *Fashion Product Images (Small)* dataset.

- **Metadata only.** We fetch a small metadata sample (~200 rows) through the
  HuggingFace **datasets-server rows REST API**. We do **not** download the
  images, and we do not vendor the dataset.
- **Fictional presentation.** The upstream `productDisplayName` field contains
  **real brand and product names** (e.g. Nike, Puma, and — critically for this
  project — adidas). Those are **discarded**: `build_item()` synthesizes a
  fictional AdidLaBs product name from the `item_id` and neutral descriptors
  (base colour + article type). Only the opaque numeric `item_id` (surfaced as
  `hf-<id>`) is retained from upstream, so downstream code has stable,
  real-looking ids to test against with **no trademark leakage**. Prices and
  deal flags are synthetic EUR values, deterministic in `item_id`.
- **Demo use.** This is a non-commercial concept demo. Please consult the
  dataset's own page/terms on HuggingFace and the original Kaggle source for the
  authoritative license before any redistribution or commercial use. AdidLaBs
  itself is MIT-licensed (© cyberaidev); the dataset license is separate and
  governs the upstream metadata.

**Concept demo - no affiliation with adidas AG. All products fictional.**

---

## Why the KB is created by boto3, not CloudFormation

The Bedrock Knowledge Base sits on **Amazon S3 Vectors**, a preview/newly-GA
vector store. Provisioning it inside the durable CloudFormation stack would
couple the whole stack's fate to a preview service — a KB/S3-Vectors failure
could roll back (or wedge) the stack. Instead `setup_kb.py` builds these
resources **out-of-band via boto3**:

- It is **idempotent**: every resource (corpus bucket, vector bucket, vector
  index, KB, data source) is looked up by a deterministic name before creation
  and reused if present. Re-running converges to the same state and returns the
  same `KB_ID`. (Proven by `tests/test_setup_kb_idempotent.py`.)
- It supports clean **`--teardown`** in reverse order (KB → data source → vector
  index → vector bucket → corpus bucket), so the preview resources can be
  removed independently before `cloudformation delete-stack`.

The vector index is configured for **Titan Text Embeddings v2**
(`amazon.titan-embed-text-v2:0`): **1024 dimensions, cosine distance,
`float32`**, with `AMAZON_BEDROCK_TEXT` / `AMAZON_BEDROCK_METADATA` marked as
non-filterable metadata keys (required by the Bedrock KB S3-Vectors
integration).

### IAM role the KB assumes (`--kb-role-arn` / `KB_ROLE_ARN`)

`setup_kb.py` does not create the role (that belongs to the infra module). The
role must allow the Bedrock KB service principal to:

- `bedrock:InvokeModel` on the Titan v2 embedding model ARN,
- `s3:GetObject` / `s3:ListBucket` on the corpus bucket,
- the S3 Vectors data-plane/control-plane actions on the vector bucket + index
  (`s3vectors:*` scoped to the two ARNs),
- and be assumable by `bedrock.amazonaws.com`.

---

## FAISS-in-Lambda fallback (documented alternative to S3 Vectors)

Because S3 Vectors is preview, the architecture carries a **no-new-always-on**
fallback that keeps the same `search_lab_knowledge` tool signature, so agents
are unaffected by the swap:

1. **Offline embed.** Embed the same `kb_docs/` corpus with Titan Text v2
   (`amazon.titan-embed-text-v2:0`, 1024-dim) chunk-by-chunk.
2. **Build a FAISS index.** Create a flat (or IVF) FAISS index over those
   vectors and serialize it, alongside a sidecar JSON of `{chunk_text, source}`
   metadata, to an object in S3 (e.g. `s3://<corpus-bucket>/faiss/index.faiss`).
3. **Load on cold start.** The MCP tool Lambda downloads the index from S3 on
   cold start and caches it for the container's warm lifetime; queries embed the
   user text (Titan v2) and run an in-process nearest-neighbour search.
4. **Same contract.** `search_lab_knowledge(query, k)` returns the top-k
   passages with source citations, identical in shape to the Bedrock KB
   `retrieve` path. Only the backend differs.

This preserves the near-zero-idle property: the index is a plain S3 object and
search runs only inside a request-scoped Lambda — no OpenSearch, no Fargate, no
clock running when idle.

---

## Notes / decisions

- **`requests`-only fetch.** We deliberately avoid the `datasets` library
  (Arrow/pandas, hundreds of MB) and hit the datasets-server REST API directly.
- **Category coverage guard.** `fetch_hf.py` treats a sample that misses any of
  the six categories as a failure and falls back — guaranteeing every category
  is represented (verified live at `--target 200`).
- **Determinism.** Prices, deals, and fictional names are all hashed from
  `item_id`, so re-seeding never churns the table and re-runs are reproducible.
- **DynamoDB floats.** `seed_dynamodb.py` converts floats to `Decimal` (DynamoDB
  rejects native floats).

---
*Concept demo - no affiliation with adidas AG. All products fictional.*

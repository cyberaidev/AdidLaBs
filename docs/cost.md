# AdidLaBs — Cost Model

> **Concept demo — no affiliation with adidas AG. All products fictional.**

This document is the **near-zero-idle review gate**. The hard requirement for AdidLaBs is that a
deployed-but-unused stack costs effectively nothing. **Reviewers reject any change that introduces
an always-on resource** — a running clock of any kind (provisioned capacity, an idle vCPU, a
reserved instance, an hourly-billed managed service). Every component below is either static
content, a request-scoped serverless function, or an on-demand data store.

Region for all resources: **`ap-southeast-2` (Sydney)**. Currency below is USD, list price, and
indicative only — the point is the **shape** of the bill (idle vs. per-use), not exact cents.

---

## 1. Idle cost — the resting state

With zero traffic, the only charges are storage of a few small objects and one dormant CloudFront
distribution. There is no per-hour line item anywhere.

| Service | Resting configuration | Idle cost/month |
|---|---|---|
| S3 (site bucket + KB corpus bucket) | a few MB of static assets + markdown | pennies (¢/GB-month) |
| CloudFront | one distribution, no traffic | ~$0 (no hourly charge) |
| Cognito user pool | demo MAU under free tier | $0 |
| API Gateway HTTP API | one API, no requests | $0 |
| Lambda × N (`api-handler`, LiteLLM, MCP tools) | 0 invocations | $0 |
| DynamoDB `adidlabs-catalog` + `adidlabs-bag` | `PAY_PER_REQUEST`, small tables | pennies (storage only) |
| Bedrock AgentCore Runtime + Gateway | registered, not invoked | $0 |
| Bedrock foundation models (via LiteLLM) | 0 tokens | $0 |
| Bedrock Knowledge Base over **S3 Vectors** (preview) | small vector index at rest | pennies |

**Idle total: a few cents per month** — dominated by S3/S3-Vectors storage of a small corpus and
catalog. Nothing scales with wall-clock time.

---

## 2. Per-service cost model (when in use)

### Edge & static — CloudFront + S3
- **S3:** storage ¢/GB-month; GET/PUT priced per request. The site is a small Vite build; the KB
  corpus is a handful of markdown files.
- **CloudFront:** per-GB data transfer out + per-10k HTTPS requests. A demo audience is negligible;
  free-tier allowances typically absorb it.
- **Access model:** bucket is private behind Origin Access Control — no public-bucket data-transfer
  surprises.

### Identity — Cognito
- Billed per **monthly active user**. The demo's handful of "join the lab" accounts sits inside the
  free tier. No user pool hourly charge.

### API — API Gateway HTTP API + Lambda
- **HTTP API:** per **million requests** (cheaper than REST APIs); no idle charge.
- **`api-handler` Lambda:** per **invocation** + **GB-second** of compute. Right-sized memory keeps
  each `/api/*` call at fractions of a cent. Weather/session calls also hit Open-Meteo, which is
  **free and keyless** (no line item).

### Data — DynamoDB (`PAY_PER_REQUEST`)
- Both tables are **on-demand**: you pay per **read/write request unit** actually consumed, plus
  storage. No provisioned capacity, no reserved-capacity floor. Seeding ~200 catalog rows is a
  one-time trickle of write units.

### Agents — Bedrock AgentCore Runtime + Gateway
- **Invocation-billed.** A styling turn triggers one orchestrator invocation and a fan-out to up to
  six category agents; cost tracks the number of turns, not time. The Gateway's MCP tool calls are
  request-scoped.

### Models — LiteLLM on Lambda → Bedrock
- **LiteLLM** is a **Lambda container** (aws-lambda-web-adapter) behind an **IAM-auth function
  URL** — stateless, **no Postgres**, **$0 idle**. It bills only as a Lambda when routing a call.
- **Bedrock tokens** are the primary variable cost. Routing keeps this cheap by design:
  - `nova-pro` (orchestrator) is used sparingly for planning/composition — one call per turn.
  - `haiku-4.5` (all category agents) is the cheap, fast, high-volume path.
  - **Model-cost verification:** do **not** assume per-token prices from memory. Confirm current
    Bedrock APAC inference-profile pricing for `apac.amazon.nova-pro-v1:0` and
    `apac.anthropic.claude-haiku-4-5-20251001-v1:0` from the official AWS Bedrock pricing page (or
    the `claude-api` reference skill for the Anthropic side) before quoting a per-turn dollar figure
    to stakeholders.

### RAG — Bedrock KB over S3 Vectors (+ Titan v2 embeddings)
- **S3 Vectors (preview):** billed on **vector storage + query volume** — pennies, and crucially
  **no ~$90+/mo OpenSearch Serverless floor**. This single choice is what keeps RAG inside the
  budget.
- **Titan Text Embeddings v2** (`amazon.titan-embed-text-v2:0`): per-token at **ingestion** time
  (one-time for the small corpus) and per query embedding. Negligible at demo scale.
- **FAISS-in-Lambda fallback** (documented in `docs/architecture.md` §3.2): if S3 Vectors is
  unavailable, the index is a single object in S3 loaded by a request-scoped Lambda — still **zero
  always-on infrastructure**.

### Optional — Tavily web search
- `search_web` defaults to **ddgs/DuckDuckGo (free)**. Tavily is used **only** when
  `TAVILY_API_KEY` is set; its cost is external to AWS and optional.

---

## 3. Illustrative demo-session cost

A single 5-minute demo (one registration, one login, session + weather fetch, ~3 stylist turns,
a few bag operations) is dominated by foundation-model tokens:

| Cost driver | Rough volume in one demo | Nature |
|---|---|---|
| CloudFront + S3 GETs | one SPA load + assets | free-tier / pennies |
| API Gateway + Lambda | ~10–20 `/api/*` calls | fractions of a cent |
| DynamoDB | a handful of reads/writes | fractions of a cent |
| Open-Meteo | 1 weather + 1 session call | free |
| AgentCore invocations | ~3 turns × (1 orchestrator + up to 6 agents) | invocation-priced |
| Bedrock tokens | the real variable cost | **verify current per-token price** |
| S3 Vectors queries | a few retrievals per turn | pennies |

**Takeaway:** a demo session lands in the low cents to low tens of cents depending on token
volume; an idle month lands in single-digit cents. There is no fixed monthly floor to amortize.

---

## 4. Review gate — rejected always-on alternatives

Any PR reintroducing one of these must be rejected:

| Rejected alternative | Idle floor | AdidLaBs choice | Idle cost |
|---|---|---|---|
| OpenSearch Serverless (vector store) | ~$90+/mo minimum | **S3 Vectors** (or FAISS-in-Lambda) | pennies / $0 |
| Fargate / ECS for LiteLLM | always-on vCPU + RAM | **LiteLLM on Lambda** (Web Adapter, IAM URL) | $0 |
| RDS / Postgres for LiteLLM state | always-on DB instance | **stateless LiteLLM**, no DB | $0 |
| Provisioned-capacity DynamoDB | reserved RCUs/WCUs | **`PAY_PER_REQUEST`** | $0 |
| EC2 / ALB web host | always-on instance + LB | **S3 + CloudFront** static | ~$0 |
| Self-hosted auth server | always-on server | **Cognito** (free-tier MAU) | $0 |
| NAT Gateway (for a VPC'd Lambda) | ~$32/mo + data | **no VPC** on request Lambdas | $0 |

**Gate checklist for reviewers:**
1. Does the change add any resource billed per **hour**, per **instance**, or by **provisioned
   capacity**? → reject.
2. Does it add a managed service with a **monthly minimum**? → reject (S3 Vectors was chosen
   precisely to avoid the OpenSearch floor).
3. Does it put a Lambda in a VPC that then needs a **NAT Gateway**? → reject or redesign.
4. Does model access still go **only** through LiteLLM routes (no hardcoded model IDs, no direct
   `bedrock:InvokeModel` from `api-handler`)? → required.
5. Are DynamoDB tables still **`PAY_PER_REQUEST`**? → required.

If all five pass, the change preserves the near-zero-idle property.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*

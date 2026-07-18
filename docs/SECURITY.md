# AdidLaBs — Security Posture

> **Concept demo — no affiliation with adidas AG. All products fictional.**

AdidLaBs is a demo, but it is built to production security defaults: **least-privilege IAM per
component (no shared god-role), no secrets in the repo, private storage behind Origin Access
Control, JWT-authorized APIs, and IAM-only access to the model gateway.** This document is the
authoritative security summary; the request stack and IAM detail live in `docs/architecture.md`
(§6).

Region: **`ap-southeast-2` (Sydney)** for all resources.

---

## 1. Identity & authentication

- **Registration + login** run through an **Amazon Cognito user pool** acting as the **AgentCore
  Identity IdP**. The "Join the lab" gate is a real sign-up; login yields a **JWT** (id/access
  token).
- The **API Gateway HTTP API** is fronted by a **JWT authorizer** bound to that user pool. Every
  `/api/*` call must present a valid `Authorization: Bearer <JWT>`.
- **`user_id` is always derived from the token `sub` claim — never trusted from the request body or
  query string.** Bag reads/writes are scoped to that `user_id` server-side, so one user cannot
  read or mutate another's bag by tampering with a payload.
- **Agent identity:** each agent presents a distinct **AgentCore workload identity**
  (`adidlabs/<agent>-xxxx`) via AgentCore Identity, so agent actions are individually attributable
  and auditable. These ids are display/identity values, not secrets.
- **`DEMO_MODE`** relaxes the *gate UX* only (accepts any well-formed input for a frictionless
  demo). It must **not** be read as a bypass of the API's JWT authorizer or of `user_id`-from-`sub`
  scoping. Keep authorization enforced even in demo mode.

## 2. Least-privilege IAM (per-component roles)

No component shares a role, and no role is broader than its job:

The API tier is **not** one `api-handler` role — it is split into a role per trust boundary so a
route only holds the grants it actually uses (the shipped `infra/template.yaml` implements this
six-role split; DynamoDB never rides along with a route that doesn't touch a table):

- **Stateless Lambda role** (`session`, `weather`, `agents`)
  - CloudWatch Logs only. Outbound HTTPS to public endpoints; **no** DynamoDB, Bedrock, or invoke
    grants.
- **Bag Lambda role** (`bag`)
  - `dynamodb:GetItem/PutItem/UpdateItem/DeleteItem/Query` on the **`adidlabs-bag` table ARN only**.
    This is the only API-tier role with table access.
  - CloudWatch Logs for its own log group.
- **Chat Lambda role** (`chat`, the orchestration `api-handler`)
  - `lambda:InvokeFunctionUrl` (IAM auth) on the **LiteLLM function URL** only.
  - `bedrock-agentcore:InvokeAgentRuntime` bounded to this account/region's runtimes, added only
    once `AGENTCORE_AGENT_ARN` is set.
  - **No `dynamodb`** (the bag route's own role owns table access) and **no `bedrock:InvokeModel`**
    — all model traffic goes through LiteLLM.
  - CloudWatch Logs for its own log group.
- **Tools Lambda role** (`tools` / MCP tools)
  - `dynamodb` item/query/scan on the **two table ARNs** (`adidlabs-catalog`, `adidlabs-bag`) for the
    catalog/deals/bag tools; `bedrock:Retrieve` on this account/region's knowledge bases; and, for
    the FAISS fallback only, `s3:GetObject` on the KB corpus bucket + `bedrock:InvokeModel` scoped to
    exactly `amazon.titan-embed-text-v2:0`.
- **LiteLLM Lambda role**
  - `bedrock:InvokeModel` / `InvokeModelWithResponseStream` scoped to the **two APAC
    inference-profile ARNs** (Nova Pro, Haiku 4.5) plus the foundation-model ARNs those profiles
    route to. Nothing else.
- **AgentCore Runtime execution role**
  - Invoke the Gateway / MCP tools; call the LiteLLM function URL.
  - `bedrock:Retrieve` on `KB_ID` (for `search_lab_knowledge`).
  - `dynamodb:*Item` / `Query` on the two tables (for catalog/deals/bag tools).
  - Assume the per-agent **workload identities** via AgentCore Identity.

Design rule: model access is **centralized in LiteLLM**. Only the LiteLLM role holds
`bedrock:InvokeModel`; agents and the API Lambda reach models *through* it via routes, never by
naming a raw model ID.

## 3. Network & data-plane exposure

- **S3 site bucket is private** — served **only** through CloudFront via **Origin Access Control**.
  No public bucket, no bucket ACLs, no website-endpoint exposure. The KB corpus bucket is likewise
  private, and `data/setup_kb.py` makes that self-enforcing: on create **and** on every rerun it
  applies **Block Public Access** (all four flags) and **default SSE-S3 encryption** to the corpus
  bucket, so the private posture holds regardless of account defaults.
- **LiteLLM function URL auth is `AWS_IAM`.** Only principals holding the explicit
  `lambda:InvokeFunctionUrl` grant (the `api-handler` and AgentCore roles) can reach it. It is
  **never public** and never anonymous.
- **CloudFront default domain only** — the demo intentionally stays on the raw `*.cloudfront.net`
  domain (no custom domain, no ACM cert to manage).
- **DynamoDB** is reached over the AWS API with IAM auth; tables are `PAY_PER_REQUEST` and hold only
  fictional catalog data and demo bag rows.
- **No VPC / NAT** on the request Lambdas — they call AWS service APIs and public endpoints
  (Open-Meteo, model routes via the IAM function URL) directly. This also avoids a NAT Gateway,
  which would violate the near-zero-idle budget.

## 4. Secrets handling — none in the repo

- **The repository contains no credentials, API keys, tokens, or account IDs.** `.gitignore`
  excludes `.env`, `*.env.*`, build output, and packaging artifacts.
- **No long-lived cloud credentials are ever shipped to the browser.** The SPA holds only the
  short-lived Cognito JWT for the signed-in session.
- **`TAVILY_API_KEY`** is **optional** and injected as an environment secret on the component that
  needs it (the `search_web` tool path) — never committed, never sent to the client. When it is
  absent, `search_web` uses the free **ddgs/DuckDuckGo** path.
- **Model IDs / routes** are configuration, not secrets, but are still centralized in LiteLLM so
  they are changed in one place.
- Deploy-time values (`KB_ID`, table names, `AGENTCORE_AGENT_ARN`, `LITELLM_URL`) are wired as
  **environment variables** by `deploy.sh` / CloudFormation outputs — not hardcoded in source.

## 5. Input, browser & privacy safety

- **Only non-sensitive fields are collected** at the gate: name, email, password (masked). The
  design explicitly forbids collecting payment methods or government/financial IDs in the browser,
  and **checkout is a labelled demo no-op** (`CHECKOUT (DEMO)`) — no payment processing occurs.
- **Location is IP-derived** server-side (`GET /api/session`) and used only to fetch a forecast; the
  user is never asked to type a location, and location is not placed in URL parameters.
- **Weather/session** use **Open-Meteo (free, keyless)** — no third-party key, no PII sent to it
  beyond an approximate lat/lon.
- Standard web hygiene applies to the SPA: JWT kept in memory/short-lived storage, HTTPS-only via
  CloudFront, no third-party trackers required for the demo.

## 6. Supply chain & runtime

- **Runtimes:** Python 3.12 for Lambdas/agents/tools; Node ≥ 20 + Vite/React for the frontend.
  Dependencies are kept minimal by design (e.g. the HF sampler uses the datasets-server REST API
  rather than the heavy `datasets` stack).
- **LiteLLM** runs as a **Lambda container image** (aws-lambda-web-adapter) — a reviewed, pinned
  image, stateless, with **no database** (no Postgres/RDS to secure or patch).
- **RAG store:** Bedrock Knowledge Base over **S3 Vectors** (preview), provisioned by
  `data/setup_kb.py` via boto3. The documented **FAISS-in-Lambda fallback** keeps the same tool
  signature and introduces **no new always-on infrastructure** to secure.

## 7. Reviewer security checklist

1. No secret, key, token, or account ID committed anywhere (grep the diff; confirm `.env` is
   ignored).
2. Every new IAM grant is **resource-scoped** and lives on a **component-specific role** — no
   wildcards on `Resource` for data/model actions, no shared role.
3. `api-handler` still has **no** `bedrock:InvokeModel`; model access remains LiteLLM-only.
4. S3 buckets remain **private + OAC**; the LiteLLM function URL remains **`AWS_IAM`**.
5. API remains behind the **Cognito JWT authorizer**; `user_id` is taken from `sub`, not the body.
6. No new **public** endpoint, and no browser-side collection of payment/sensitive IDs.
7. `DEMO_MODE` does not disable the authorizer or `user_id` scoping.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*

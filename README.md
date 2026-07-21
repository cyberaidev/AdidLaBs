<h1 align="center">
  ADID<em>L</em>A<em>B</em>S
</h1>

<p align="center"><strong>Weather-aware AI shopping demo on Amazon Bedrock AgentCore.</strong></p>

<p align="center">
  <em>Concept demo — no affiliation with adidas AG. All products fictional.</em>
</p>

---

> The wordmark reads **ADID·*L*·A·*B*·S** — the italic **L** and **B** are the amber "lab"
> highlight (rendered as styled text in the app via `<Wordmark>`, not an image). GitHub
> markdown can only approximate it with `<em>` italics; see
> [`docs/design.md`](docs/design.md) §1.1 for the authoritative brand device.

## Pitch

AdidLaBs is a fictional storefront that dresses you for the sky. A shopper joins "the lab,"
signs in, and the site reads their IP-based location, local time, and a 3-day forecast, then a
mesh of specialist agents on **Amazon Bedrock AgentCore** — a Nova Pro orchestrator supervising a
Haiku 4.5 weather agent and six Haiku 4.5 category agents — assembles weather-matched outfit picks through a live stylist
chat. It is an end-to-end reference for an agentic retail experience engineered around a single
hard constraint: **near-zero cost when idle** — no OpenSearch, no Fargate, no always-on compute.
Every component is static content, a request-scoped serverless function, or an on-demand store.

## Architecture

A React SPA on CloudFront/S3 talks to an API Gateway HTTP API backed by a Python 3.12
`api-handler` Lambda. That Lambda serves session/weather/bag/agents endpoints and, on
`POST /api/chat`, invokes an AgentCore Runtime hosting a LangGraph orchestrator. Agents reach
foundation models **only through LiteLLM routes** (`nova-pro`, `haiku-4.5`) mapped to APAC
cross-region inference profiles, and reach data + knowledge through **MCP tools** on the AgentCore
Gateway (DynamoDB catalog/bag, a Bedrock Knowledge Base over Amazon S3 Vectors, and a free web
fallback). Everything lives in **`ap-southeast-2` (Sydney)**.

- **[`docs/architecture.md`](docs/architecture.md)** — full request stack, agent mesh, RAG design, IAM posture, deploy/teardown, with Mermaid diagrams.
- **[`docs/design.md`](docs/design.md)** — brand + UI specification (v3 mockup): wordmark, tokens, components, copy deck, state/flow.
- **[`docs/cost.md`](docs/cost.md)** — per-service cost model and the near-zero-idle review gate.
- **[`docs/demo-script.md`](docs/demo-script.md)** — 5-minute demo walkthrough.
- **[`docs/SECURITY.md`](docs/SECURITY.md)** — IAM posture, secrets handling, threat notes.

```
User → CloudFront + S3 (static React)
     → API Gateway HTTP API (JWT authorizer → Cognito)
       → Lambda api-handler (Python 3.12)
         → DynamoDB adidlabs-catalog / adidlabs-bag (PAY_PER_REQUEST)
         → Open-Meteo (free, keyless) for weather/session
         → AgentCore Runtime (LangGraph: 1 orchestrator + 7 agents)
             → AgentCore Gateway (MCP tools)
             → LiteLLM on Lambda (Web Adapter, IAM function URL) → Bedrock APAC profiles
             → Bedrock Knowledge Base over S3 Vectors (Titan v2; FAISS-in-Lambda fallback)
```

## Quickstart

Prerequisites: **AWS CLI v2** with credentials for an account you can deploy into, **Node ≥ 20**,
**Python 3.12**, and **Docker** (for the LiteLLM container image). Everything targets
`ap-southeast-2`.

```bash
git clone https://github.com/cyberaidev/AdidLaBs.git
cd AdidLaBs

# optional: enable Tavily web search (else the free ddgs/DuckDuckGo path is used)
export TAVILY_API_KEY=...   # optional

# deploy the whole stack (build → cfn → seed → KB → agents → gateway)
./deploy.sh

# ... demo, then drive cost to zero
./teardown.sh
```

`deploy.sh` prints the CloudFront site URL, the API base URL, and the LiteLLM function URL when it
finishes. The demo stays on the **raw CloudFront domain** (no custom domain by design).

## Module map

| Path | What it is |
|---|---|
| `frontend/` | Vite + React SPA (storefront, stylist chat, agent roster, drawers) |
| `infra/` | CloudFormation template + params for the durable serverless stack |
| `backend/` | Python 3.12 API Lambda handlers (`/api/session`, `/api/weather`, `/api/bag`, `/api/chat`, `/api/agents`, `/api/catalog`, `/api/terminal`, `/api/telemetry`) |
| `gateway/` | LiteLLM model-access tier (aws-lambda-web-adapter) + route config, IAM function URL |
| `agents/` | AgentCore LangGraph orchestrator + weather agent + 6 category agents |
| `mcp-tools/` | MCP tool implementations for the AgentCore Gateway |
| `data/` | HF sampling, DynamoDB seed, KB corpus generation, `setup_kb.py`, `synthetic_fallback.json` |
| `docs/` | Architecture, design, cost, demo-script, security |
| `deploy.sh` / `teardown.sh` | Ordered stack orchestration and its exact reverse |

> Module directories other than `docs/` are populated by their respective creators; this README,
> the license, ignore rules, and the deploy/teardown scripts are the docsroot module.

## Post-release enhancements

Shipped after the initial release (see `git log` for the full trail):

- **AI-choice shopping.** On first login the orchestrator pre-fills the bag with a
  forecast-matched starter kit; rows are tagged **AI CHOICE**. Chat turns with add
  intent ("add a rain jacket to my bag") drop that turn's picks into the bag tagged
  **AI ADVICE**. Manual picks stay untagged so shoppers can curate. Prices in **USD**.
- **Per-agent web terminal.** Every agent card opens a read-only terminal drawer that
  tails the AgentCore runtime's CloudWatch log group live (`GET /api/terminal`,
  JWT-protected), filtered by that agent's workload identity; the orchestrator emits
  wid-tagged `[session]` / `[a2a]` lines per turn.
- **LiteLLM telemetry panel.** `GET /api/telemetry` aggregates CloudWatch
  `AWS/Bedrock` metrics (tokens in/out, invocations, latency) per model route;
  the storefront panel refreshes every 60 s with an incremental this-visit delta.
  Agent LLM calls are SigV4-signed against the IAM-auth LiteLLM function URL.
- **Catalog browsing.** `GET /api/catalog` (public) lists the full category
  inventory; BROWSE THE FULL CATALOG links open a searchable drawer per category.
- **Account panel.** User details, session claims, sign-out, and OpenClaw / Hermes
  agent-connection stubs (simulated A2A handshake — browser-local state only).
- **Brand device.** The amber serif **L** and **B** lie fallen flat on the baseline
  in the wordmark and the hero headline; persistent chat history per session;
  registration auto-confirm (demo-only Cognito pre-sign-up trigger); no-cache
  `index.html` + immutable hashed assets.

## Agent roster

Eight agents on Bedrock AgentCore, each with an **AgentCore workload identity id** the frontend
renders verbatim. The orchestrator uses the stronger `nova-pro` route; every other agent uses
`haiku-4.5`. All in `ap-southeast-2`.

| Agent | Workload identity id | Model route |
|---|---|---|
| Orchestrator (supervisor) | `adidlabs/orchestrator-9f21` | `nova-pro` |
| Weather | `adidlabs/weather-3b7c` | `haiku-4.5` |
| Shoes | `adidlabs/shoes-4e2a` | `haiku-4.5` |
| Pants | `adidlabs/pants-8c1d` | `haiku-4.5` |
| T-shirt | `adidlabs/tshirt-2a9e` | `haiku-4.5` |
| Jumper | `adidlabs/jumper-6d3f` | `haiku-4.5` |
| Jacket | `adidlabs/jacket-1e8b` | `haiku-4.5` |
| Accessory | `adidlabs/accessory-5c4a` | `haiku-4.5` |

Routes resolve through LiteLLM: `nova-pro → bedrock/apac.amazon.nova-pro-v1:0`,
`haiku-4.5 → bedrock/apac.anthropic.claude-haiku-4-5-20251001-v1:0` (APAC cross-region inference
profiles). Application code never names a raw model ID.

## Cost (near-zero idle)

Every service is request-scoped or storage-priced — nothing runs a clock. Full model in
[`docs/cost.md`](docs/cost.md).

| Service | Idle cost | Billed on |
|---|---|---|
| CloudFront + S3 (static site) | ~$0 | requests / GB transferred + stored |
| Cognito user pool | $0 | MAU (free tier covers the demo) |
| API Gateway HTTP API | $0 | requests |
| Lambda (`api-handler`, LiteLLM, MCP tools) | $0 | invocations + GB-seconds |
| DynamoDB (`PAY_PER_REQUEST`) | $0 | read/write request units + storage |
| Bedrock AgentCore Runtime + Gateway | $0 | invocations |
| Bedrock models (via LiteLLM) | $0 | tokens per request |
| Bedrock KB over **S3 Vectors** (preview) | pennies | storage + queries (no OpenSearch floor) |

Rejected because they carry an always-on floor: OpenSearch Serverless (~$90+/mo), Fargate/ECS for
LiteLLM, RDS/Postgres for LiteLLM state, provisioned-capacity DynamoDB, EC2 web hosting. A
deployed-but-unused stack costs effectively nothing; `teardown.sh` drives it to zero.

## Mock data & attribution

Catalog data is sampled from the HuggingFace dataset
**[`ashraq/fashion-product-images-small`](https://huggingface.co/datasets/ashraq/fashion-product-images-small)** —
**metadata only**, ~200 rows fetched via the datasets-server rows REST API (no heavy
dependencies), mapped to six categories (shoes, pants, tshirt, jumper, jacket, accessory) with
**synthetic EUR prices and deals**. When HuggingFace is unreachable, `data/synthetic_fallback.json`
(~40 items) is used instead. No product images are redistributed; imagery in the app is fictional
or synthetic. See `data/README.md` for the dataset attribution and license note.

## License

Released under the **MIT License**, © **cyberaidev**. See [`LICENSE`](LICENSE).
Repository: [github.com/cyberaidev/AdidLaBs](https://github.com/cyberaidev/AdidLaBs).

---

<p align="center"><em>Concept demo — no affiliation with adidas AG. All products fictional.</em></p>

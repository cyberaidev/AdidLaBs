# AdidLaBs — Integration Scorecard

> **Concept demo — no affiliation with adidas AG. All products fictional.**

Final integration pass by the JUDGER agent. Every module was scored against the
build contract and cross-checked for consistency (table names, `/api` routes,
env var names, LiteLLM route names, model IDs, agent workload identities, and
region). The quality gate requires every module to **exceed 95**.

## Module scores

| Module | Score | Gate (> 95) |
|---|---|---|
| infra | 97 | PASS |
| frontend | 97 | PASS |
| backend | 97 | PASS |
| gateway | 96 | PASS |
| agents | 97 | PASS |
| mcp-tools | 97 | PASS |
| data | 97 | PASS |
| docsroot | 97 | PASS |

**All eight modules exceed 95 → gate PASSED.**

Fix rounds used: **4**

## Integration findings

Cross-module contract verification (grepped across the entire repo). **No
inconsistencies were found; no files required editing in this pass.**

### Contracts verified consistent

- **Region.** `ap-southeast-2` (Sydney) is used uniformly across `deploy.sh`,
  `teardown.sh`, `infra/template.yaml`, all backend/agents/mcp-tools Python,
  `agents/agentcore.yaml`, `gateway/config.yaml`, and the frontend copy. The
  only `ap-southeast-1` / `ap-northeast-1` occurrences are the **member regions
  of the APAC cross-region inference profiles** inside IAM resource ARNs in
  `infra/template.yaml` (expected and correct), plus one example comment in
  `gateway/lambda/resolve_lwa_layer_arn.sh`.
- **DynamoDB tables.** `adidlabs-catalog` (pk `item_id`) and `adidlabs-bag`
  (pk `user_id`, sk `item_id`), both `PAY_PER_REQUEST`, consistent in infra,
  data seeder, backend, mcp-tools, agents, and docs. `catalog.json` has 200
  items with an `item_id` primary key, the six contract categories, and EUR
  pricing.
- **API routes.** Exactly the five contract route groups appear on the HTTP API
  (`GET /api/session`, `GET /api/weather`, `GET|POST|DELETE /api/bag`,
  `POST /api/chat`, `GET /api/agents`). All `/api/catalog` mentions are explicit
  negative statements documenting that no such endpoint exists — not a route.
- **Env vars.** `LITELLM_URL`, `KB_ID`, `CATALOG_TABLE`, `BAG_TABLE`,
  `AGENTCORE_AGENT_ARN`, `DEMO_MODE`, `TAVILY_API_KEY` — exact names used
  everywhere; no stray variants (no `*_TABLE_NAME`, `DYNAMO_TABLE`, etc.).
- **LiteLLM routes / model IDs.** Two routes only. `nova-pro →
  bedrock/apac.amazon.nova-pro-v1:0` and `haiku-4.5 →
  bedrock/apac.anthropic.claude-haiku-4-5-20251001-v1:0` agree across
  `agents/common/llm.py` (`ROUTE_TARGETS`), `gateway/config.yaml`,
  `agents/agentcore.yaml`, and the in-template LiteLLM shim. Orchestrator uses
  `nova-pro`; all other agents use `haiku-4.5`.
- **Agent workload identities.** All eight WIDs
  (`adidlabs/orchestrator-9f21`, `weather-3b7c`, `shoes-4e2a`, `pants-8c1d`,
  `tshirt-2a9e`, `jumper-6d3f`, `jacket-1e8b`, `accessory-5c4a`) match exactly
  across `agents/common/roster.py`, `frontend/src/copy.js`, the
  `/api/agents` roster in `infra/template.yaml`, and the README. No stray or
  invented identities. The frontend `AgentCard` renders `wid` and route chip
  verbatim.
- **MCP tools.** `server.TOOL_SPECS` is the single source of truth and contains
  exactly `get_catalog`, `get_deals`, `bag_add`, `bag_get`,
  `search_lab_knowledge`, `search_web`; `register_gateway.py` enumerates the
  same set. `search_web` defaults to free ddgs/DuckDuckGo and switches to Tavily
  only when `TAVILY_API_KEY` is set.
- **Embeddings / KB.** `amazon.titan-embed-text-v2:0` for embeddings; the RAG
  store is a Bedrock Knowledge Base over Amazon S3 Vectors (preview), created
  out-of-band by `data/setup_kb.py`; the FAISS-in-Lambda fallback is documented
  and its dormant Titan `InvokeModel` grant is present.
- **Runtimes.** All Lambdas are `python3.12`; the frontend requires Node >= 20
  with Vite + React.
- **Cost posture.** No OpenSearch, Fargate/ECS, provisioned concurrency, or NAT
  Gateway is provisioned. Those terms appear only in "rejected/avoided"
  rationale. LiteLLM runs on Lambda behind an IAM-auth function URL.

### README links

All relative links in the root README and every module/`docs` README resolve to
files that exist (`LICENSE`, `docs/SECURITY.md`, `docs/architecture.md`,
`docs/cost.md`, `docs/demo-script.md`, `docs/design.md`, and cross-module
references). No broken links.

### Trademark scan

Grepped for `adidas`, `trefoil`, and `three stripes`. Every hit is inside an
**allowed** context:

- the no-affiliation disclaimer ("no affiliation with adidas AG. All products
  fictional."), present in the footer copy and every public-facing doc;
- policy-negation statements describing what is deliberately excluded ("No
  adidas trademarks — no three stripes, no trefoil, no adidas product names");
- the data pipeline's trademark-scrubbing logic in `data/category_map.py` and
  its tests, which explicitly discard real brand strings from the source
  HuggingFace rows and assert they never reach the catalog.

The actual product data (`catalog.json`, `synthetic_fallback.json`,
`frontend/src/data/fallbackCatalog.js`) contains **no** adidas product names,
three-stripe motif, trefoil, or other brand device. Mock data carries the
HuggingFace `ashraq/fashion-product-images-small` attribution and a separate
license note. Project license is MIT © cyberaidev, targeting
`github.com/cyberaidev/AdidLaBs`.

## Verdict

Contracts are consistent across every module, README links are valid, no adidas
trademarks appear outside the permitted disclaimer/attribution/policy contexts,
and all eight module scores exceed the 95 gate. **APPROVED.**

*Concept demo — no affiliation with adidas AG. All products fictional.*

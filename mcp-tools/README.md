# AdidLaBs — MCP Tools Server

> **Concept demo — no affiliation with adidas AG. All products fictional.**

The MCP tool surface for the AdidLaBs weather-aware shopping demo. A single
[FastMCP](https://github.com/modelcontextprotocol/python-sdk) server exposes six
**LLM-free** tools that the Bedrock AgentCore agent mesh (orchestrator + seven
specialists) calls through an **AgentCore Gateway**.

Structured facts (price, stock, deals, bag) are plain DynamoDB lookups so they
stay deterministic and cheap. Only narrative knowledge goes through RAG
(`search_lab_knowledge`), which degrades gracefully to web search on a miss.

**Region: `ap-southeast-2` (Sydney).** Every AWS resource lives there. Models are
never touched here — these tools do no inference.

---

## Tools

| Tool | Backend | Purpose |
|---|---|---|
| `get_catalog` | DynamoDB `adidlabs-catalog` (pk `item_id`) | Price/stock/category lookups by `category` or `item_id`. Not RAG. |
| `get_deals` | DynamoDB `adidlabs-catalog` | Discounted items (`deal_pct > 0`), best discount first. |
| `bag_add` | DynamoDB `adidlabs-bag` (pk `user_id`, sk `item_id`) | Add/upsert an item into a user's bag. `user_id` comes from the JWT `sub`. |
| `bag_get` | DynamoDB `adidlabs-bag` | Read a user's current bag + EUR subtotal. |
| `search_lab_knowledge` | Bedrock KB `retrieve` (`KB_ID`) | Semantic RAG over the lab corpus; returns chunks + relevance scores; **degrades to `search_web`** when the KB is unavailable. |
| `search_web` | `ddgs`/DuckDuckGo (free) or Tavily | KB-miss fallback. Every result is marked `web_sourced: true`. |

### Score gating (KB vs web)

`search_lab_knowledge` returns a stable envelope so the orchestrator can decide
whether to ground on brand knowledge or fall back to the web **deterministically**
(no LLM in the loop):

```json
{
  "source": "kb",
  "degraded": false,
  "query": "waterproof jacket fabric",
  "count": 2,
  "top_score": 0.82,
  "threshold": 0.40,
  "relevant": true,
  "results": [{"text": "...", "score": 0.82, "source_uri": "s3://..."}]
}
```

- `relevant` is `true` only when there is at least one hit **and** `top_score >=`
  `KB_RELEVANCE_THRESHOLD` (0.40). When `false`, the orchestrator calls
  `search_web`.
- On KB failure (unset `KB_ID`, or `retrieve` raises — e.g. an S3 Vectors preview
  hiccup) the tool transparently calls `search_web` and returns the **same
  envelope keys** with `source: "web"`, `degraded: true`, `relevant: false`, and a
  `degrade_reason`. Agents need no signature change.

---

## Environment variables

Exact names (shared across the whole project):

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `CATALOG_TABLE` | `get_catalog`, `get_deals` | `adidlabs-catalog` | Catalog table name. |
| `BAG_TABLE` | `bag_add`, `bag_get` | `adidlabs-bag` | Bag table name. |
| `KB_ID` | `search_lab_knowledge` | *(unset → degrade to web)* | Bedrock Knowledge Base id from `data/setup_kb.py`. |
| `TAVILY_API_KEY` | `search_web` | *(unset → ddgs)* | Optional; switches web search to Tavily REST. |
| `AGENTCORE_GATEWAY_ID` | `register_gateway.py` | *(see precedence below)* | Preferred env var naming the gateway to register targets into. |
| `GATEWAY_ID` | `register_gateway.py` | *(see precedence below)* | Alternative env var for the gateway id; used only when `AGENTCORE_GATEWAY_ID` is unset. |
| `MCP_SERVER_ENDPOINT` | `register_gateway.py` | `mcp://adidlabs-tools` | MCP endpoint each gateway target invokes. |

**Gateway-id resolution precedence** (`_resolve_gateway_id`), first match wins:

1. the `--gateway-id` CLI flag, then
2. the `AGENTCORE_GATEWAY_ID` env var, then
3. the `GATEWAY_ID` env var, then
4. the built-in demo literal `adidlabs-tools-gw`.

So `adidlabs-tools-gw` is only the *final* fallback when the flag and both env
vars are unset — it is not the default value of `AGENTCORE_GATEWAY_ID` alone.

`AGENTCORE_AGENT_ARN`, `LITELLM_URL`, and `DEMO_MODE` are consumed elsewhere in
the stack (api-handler / agents); the tools themselves never call a model.

---

## Run

Install and launch the MCP server (stdio transport, as hosted by the gateway):

```bash
pip install -r requirements.txt
python server.py
```

Register the tools as AgentCore Gateway targets:

```bash
# Preview the plan without any AWS call:
python register_gateway.py --dry-run

# Register against the configured gateway:
AGENTCORE_GATEWAY_ID=<your-gateway-id> python register_gateway.py
```

`register_gateway.py` enumerates the canonical `server.TOOL_SPECS` registry, so
the gateway targets and the live MCP surface can never drift apart. Each tool
fails independently — one registration error does not abort the batch, and the
process exits non-zero if any target failed.

---

## Tests

All boto3 and network I/O is stubbed — **no real DynamoDB, Bedrock KB, ddgs, or
Tavily traffic**. In-memory fakes live in `tests/conftest.py`.

```bash
pip install -r requirements.txt
pytest
```

Coverage:

- `test_dynamodb_tools.py` — catalog/deals filtering + limits, bag read scoped to
  `user_id` with subtotal, bag upsert write assertions, input validation,
  non-positive-`qty` clamping (a negative qty can never persist into the
  subtotal), and multi-page `get_deals` accumulation (matched deals surface and
  the `limit` is honoured even when a single scan page under-returns matches).
- `test_knowledge_and_web.py` — the three contract paths:
  1. **KB-available** (high score → `relevant: true`),
  2. **score-gating** (low/empty score → `relevant: false`),
  3. **KB-degraded-to-web** (unset `KB_ID` and `retrieve` exception → web
     fallback with the KB envelope shape); plus `search_web` provider selection
     (ddgs default vs Tavily when keyed) and the missing-`ddgs` graceful path.
- `test_register_gateway.py` — all six tools registered as targets, dry-run makes
  no AWS call, per-tool failure reporting, exit codes, gateway-id precedence, and
  target payload shape.

Latest run: **28 passed**.

---

## RAG backend & FAISS-in-Lambda fallback

`search_lab_knowledge` targets a **Bedrock Knowledge Base over Amazon S3 Vectors**
(preview), created by `data/setup_kb.py` via boto3 (not CloudFormation, since S3
Vectors is preview). Embeddings use `amazon.titan-embed-text-v2:0`.

Because S3 Vectors is preview, the design carries a **no-new-infrastructure
fallback**: embed the same corpus with Titan v2 offline, build a **FAISS** index,
and store the index file on S3. The tool Lambda loads that index on cold start
(cached for the warm container lifetime) and serves nearest-neighbour queries
in-process. `search_lab_knowledge` keeps the same signature and envelope, so
agents are unaffected by the swap. This preserves the near-zero-idle property:
the index is just an S3 object, and search runs only inside a request-scoped
Lambda. Today the tool already degrades to `search_web` whenever the KB path is
unavailable, so the mesh keeps working even before the FAISS index is wired.

---

## License & attribution

MIT © cyberaidev — `github.com/cyberaidev/AdidLaBs`.

Mock data: HuggingFace `ashraq/fashion-product-images-small` (metadata only),
synthetic EUR prices.

*Concept demo — no affiliation with adidas AG. All products fictional.*

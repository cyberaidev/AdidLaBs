# AdidLaBs — Agent Mesh

> **Concept demo — no affiliation with adidas AG. All products fictional.**

A Python **LangGraph** supervisor + specialist mesh that runs on **Amazon
Bedrock AgentCore** and answers the storefront's `POST /api/chat`. It reads a
3‑day forecast, decides which clothing categories matter, fans out to category
specialists over **A2A**, and composes one weather‑matched stylist reply grounded
in the lab knowledge base.

Region: **`ap-southeast-2` (Sydney)**. Models are reached **only** through the two
named **LiteLLM routes** — no agent ever names a raw Bedrock model id.

---

## Roster

| Agent | Workload identity (`wid`) | Route |
|---|---|---|
| Orchestrator (supervisor) | `adidlabs/orchestrator-9f21` | `nova-pro` |
| Weather | `adidlabs/weather-3b7c` | `haiku-4.5` |
| Shoes | `adidlabs/shoes-4e2a` | `haiku-4.5` |
| Pants | `adidlabs/pants-8c1d` | `haiku-4.5` |
| T‑shirt | `adidlabs/tshirt-2a9e` | `haiku-4.5` |
| Jumper | `adidlabs/jumper-6d3f` | `haiku-4.5` |
| Jacket | `adidlabs/jacket-1e8b` | `haiku-4.5` |
| Accessory | `adidlabs/accessory-5c4a` | `haiku-4.5` |

The single source of truth is [`common/roster.py`](common/roster.py); the frontend
and `GET /api/agents` render these `wid`s verbatim.

---

## The styling graph

```
weather_read ──▶ route ──▶ fan_out (A2A) ──▶ compose
```

1. **`weather_read`** — [`weather_agent.py`](weather_agent.py) normalizes an
   Open‑Meteo 3‑day daily payload (WMO weather codes) into a structured
   `Conditions` object: a *dominant* band (`rain` / `sun` / `cold` / `mild`),
   temperature range, wetness flag, and a short read.
2. **`route`** — [`orchestrator.py`](orchestrator.py) picks the specialists to
   consult. This step is **deterministic** (see the contract below) so it is
   testable with a mocked LLM. An explicit user request may *widen* the set
   (e.g. "also a jacket"), but can never drop a mandated category.
3. **`fan_out`** — sends an A2A `style_pick` task envelope to each chosen
   specialist and collects replies.
4. **`compose`** — merges picks + citations into one reply (via the `nova-pro`
   route when an LLM is present; a deterministic template otherwise).

### Routing contract (exercised by tests)

| Dominant condition | Specialists consulted |
|---|---|
| **rain** | **jacket + accessory** |
| **sun** | **tshirt + shoes** |
| cold | jumper + jacket |
| mild | tshirt + pants |

Encoded in `ROUTING_RULES` / `route_for_conditions()`.

---

## A2A envelopes & the in‑process tradeoff (documented)

Specialists are addressed with a small transport‑agnostic **task envelope**
([`common/a2a.py`](common/a2a.py)): `TaskEnvelope` in, `TaskResult` out,
correlated by `task_id`. Both are pure JSON‑serialisable dataclasses.

**We deliver those envelopes *in‑process*** — the orchestrator calls each
specialist's `handle()` directly inside **one** AgentCore runtime.

- **Why in‑process:** the hard project constraint is *near‑zero idle cost*.
  One runtime hosting the whole graph means one warm container, one cold start,
  one scaling unit — versus **eight** runtimes (an orchestrator + seven agents)
  each with its own idle/cold‑start/network overhead and per‑runtime billing.
- **The tradeoff:** in‑process A2A gives up independent per‑agent scaling,
  isolation, and separate deploy cadence. For a demo‑scale, bursty chat workload
  that is the right call.
- **Why it's cheap to change later:** because the envelope is transport‑agnostic,
  moving a specialist to its own remote AgentCore runtime is a delivery swap
  (`agent.handle(env)` → post `env.to_dict()` to that runtime and parse the
  `TaskResult`) with **no change** to any agent's logic. Workload identities are
  already distinct per agent, so the audit story is unchanged.

---

## Knowledge grounding (KB → web fallback)

Each specialist grounds its rationale with `search_lab_knowledge` (Bedrock KB
`retrieve` over Amazon **S3 Vectors**; Titan Text v2 embeddings). If the top
passages fall **below the relevance floor** (`KB_RELEVANCE_FLOOR`, see
[`common/tools.py`](common/tools.py)), it falls back to `search_web`
(ddgs/DuckDuckGo by default, Tavily when `TAVILY_API_KEY` is set). Structured
facts (price, stock, deals) stay on plain DynamoDB tools (`get_catalog` /
`get_deals`) — only narrative knowledge goes through RAG.

**FAISS‑in‑Lambda fallback.** Because S3 Vectors is preview, the design carries a
no‑new‑infra fallback: embed the same corpus with Titan v2 offline, store a FAISS
index on S3, and have the MCP tool Lambda load it on cold start and serve
nearest‑neighbour queries in‑process. `search_lab_knowledge` keeps the same
signature, so agents are unaffected by the swap.

---

## Model access — routes only

```
nova-pro   →  bedrock/apac.amazon.nova-pro-v1:0                    (orchestrator)
haiku-4.5  →  bedrock/au.anthropic.claude-haiku-4-5-20251001-v1:0 (everyone else)
```

All calls go through the OpenAI‑compatible **LiteLLM** gateway at `LITELLM_URL`
([`common/llm.py`](common/llm.py)). `resolve_route()` rejects anything that
isn't one of the two route names, so a raw model id can never leak into a
request. A model swap is a one‑line LiteLLM config change — no agent code moves.

---

## Files

| Path | Role |
|---|---|
| `common/llm.py` | OpenAI‑compatible LiteLLM client; route validation |
| `common/a2a.py` | A2A task envelope / result helpers |
| `common/roster.py` | Workload identities + route assignments (source of truth) |
| `common/tools.py` | MCP tool surface + in‑process demo/CI client + KB‑miss gate |
| `weather_agent.py` | Open‑Meteo → structured 3‑day `Conditions` |
| `shopping_agents.py` | Six category specialists (persona + filtering + grounding) |
| `orchestrator.py` | LangGraph supervisor: weather → route → fan‑out → compose |
| `entrypoint.py` | `BedrockAgentCoreApp` exposing the graph (`app`) |
| `agentcore.yaml` | AgentCore runtime config for the starter toolkit |
| `deploy_agents.sh` | Pre‑deploy compile check + `agentcore configure`/`launch` |
| `requirements.txt` / `requirements-dev.txt` | Runtime / dev deps |
| `tests/` | Routing‑contract + tools + LLM‑client tests (mocked LLM) |

---

## Environment variables

`LITELLM_URL`, `KB_ID`, `CATALOG_TABLE`, `BAG_TABLE`, `AGENTCORE_AGENT_ARN`,
`DEMO_MODE`, `TAVILY_API_KEY` (optional). See
[`../docs/architecture.md`](../docs/architecture.md) §5 for the full contract.

---

## Run it

```bash
# Runtime deps (LangGraph + AgentCore SDK). Both have in-process fallbacks, so
# tests run even without them installed.
pip install -r requirements.txt

# Dev/CI: add pytest.
pip install -r requirements-dev.txt

# Routing-contract tests — mocked LLM, no live Bedrock, no network.
python -m pytest

# Smoke the graph end-to-end (uses the in-process tool client under DEMO_MODE).
echo '{"message":"what should I wear?","forecast":{"daily":{"time":["2026-07-18"],"weathercode":[61],"temperature_2m_max":[14],"temperature_2m_min":[9]}}}' \
  | DEMO_MODE=1 python -m agents.entrypoint
```

### Design decisions

- **Graceful degradation everywhere.** If LangGraph is absent the graph runs via
  an equivalent in‑process sequential runner with the *same* `invoke` API; if the
  AgentCore SDK is absent `entrypoint.py` exports a compatible local `app`. This
  keeps `import`/compile green in CI and local dev without a cloud round‑trip.
- **Deterministic core, optional LLM.** Weather normalization, routing, and
  catalog filtering are deterministic; the LLM only *writes prose* (weather read,
  rationale, final reply). If a model call fails, a template stands in — a bad
  model call never sinks a styling turn, and the routing contract always holds.
- **Ship after backend.** With the backend live, set `DEMO_MODE=0` and wire the
  real Gateway MCP client in `common/tools.default_tool_client()`; `deploy_agents.sh`
  verifies the entrypoint imports and the graph compiles before it launches.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*

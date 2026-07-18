# AdidLaBs — Backend (Lambda handlers)

> **Concept demo — no affiliation with adidas AG. All products fictional.**

Python 3.12 AWS Lambda handlers behind the AdidLaBs HTTP API. Five request-scoped
functions power the storefront: session/geolocation, weather, bag CRUD, stylist
chat, and the agent roster. Everything is engineered for **near-zero idle cost** —
no always-on compute; each handler runs only per request.

- **Region:** `ap-southeast-2` (Sydney). All resources live here.
- **Runtime:** Python 3.12.
- **Model access:** handlers never name a raw model id. `/api/chat` invokes the
  **AgentCore Runtime** orchestrator, which reaches Bedrock **only** through the
  LiteLLM gateway (routes `nova-pro` for the orchestrator, `haiku-4.5` for the
  category agents).

---

## Routes → handlers

| Method(s) | Path | Handler | Purpose |
|---|---|---|---|
| `GET` | `/api/session` | `session.handler` | Server time + IP geolocation |
| `GET` | `/api/weather` | `weather.handler` | 3-day forecast (Open-Meteo, keyless) |
| `GET` `POST` `DELETE` | `/api/bag` | `bag.handler` | Bag CRUD on `adidlabs-bag` |
| `POST` | `/api/chat` | `chat.handler` | Stylist turn (orchestrator → agents) |
| `GET` | `/api/agents` | `agents.handler` | Agent roster + wid identities + status |

Every handler also answers `OPTIONS` with a `204` CORS preflight. **Every**
response — success, error, and preflight — carries CORS headers via
`common.http.respond`.

---

## File layout

```
backend/
├── common/
│   ├── __init__.py
│   ├── http.py        # CORS, JSON responses, body/query parsing, JWT user_id
│   └── geo.py         # CloudFront-header + ip-api.com geolocation (Sydney fallback)
├── session.py         # GET  /api/session
├── weather.py         # GET  /api/weather
├── bag.py             # GET/POST/DELETE /api/bag
├── chat.py            # POST /api/chat  (DEMO_MODE canned reply | AgentCore invoke)
├── agents.py          # GET  /api/agents
├── requirements.txt
├── pytest.ini
└── tests/             # botocore-stubbed unit tests, zero network calls
```

---

## Handler behaviour

### `session.py` — geolocation
Resolves an approximate caller location, **preferring CloudFront viewer headers**
(`cloudfront-viewer-latitude` / `-longitude` / `-city` / `-time-zone`, forwarded
at the edge — no network call). If those are absent it falls back to the keyless
**ip-api.com** endpoint, and finally to a **Sydney** default so the weather bar
always renders. Also returns server UTC time and a local time computed from the
resolved timezone (`zoneinfo`, backed by the bundled `tzdata` package, degrading
to UTC only if tzdata is ever absent). The user is never asked to type a location.

### `weather.py` — forecast
Calls **Open-Meteo** (`api.open-meteo.com`, no API key) for a 3-day daily forecast
at `?lat=&lon=` (Sydney default when omitted). WMO weathercodes are mapped to
sun/cloud/rain/snow emoji (mapping documented inline). Upstream failures return
`502`; bad coordinates return `400`.

### `bag.py` — bag CRUD
Reads/writes the `adidlabs-bag` DynamoDB table (pk `user_id`, sk `item_id`,
`PAY_PER_REQUEST`). The `user_id` is **always** derived from the JWT `sub` claim
(`common.http.get_user_id`) — never the request body (architecture Sec. 6). `POST`
upserts a row and **accumulates `qty`** on repeat adds (`bag_add` semantics);
`GET` returns rows + computed totals (`bag_get`); `DELETE ?item_id=` removes
one row. `Decimal` values are normalized to int/float for JSON.

Every `GET`/`POST`/`DELETE` returns the full bag with these fields:

| Field | Meaning |
|---|---|
| `items` | The bag rows (`item_id`, `qty`, `title`, `category`, `price`, `image`) |
| `count` | Number of **distinct line items** (`len(items)` — a single row of `qty: 3` counts as `1`) |
| `total_qty` | Sum of **per-line quantities** (a single row of `qty: 3` counts as `3`) |
| `subtotal` | `Σ price × qty`, rounded to 2 dp |

> **Frontend note:** the two counts are intentionally distinct — do **not**
> conflate them. Use `count` for a "distinct products" label and `total_qty`
> for a "total units in bag" badge. A bag with one row of `qty: 2` and another
> of `qty: 3` reports `count: 2`, `total_qty: 5`.

### `chat.py` — stylist turn
Two paths, chosen automatically:

- **Demo path** (`DEMO_MODE=1` **or** `AGENTCORE_AGENT_ARN` unset): returns a
  polished, **weather-matched** canned stylist reply composed from the posted
  session context (city + 3-day forecast). It reads like the `nova-pro`
  orchestrator handed off to the `haiku-4.5` category agents, credits every agent
  with its **real wid identity**, and includes fictional picks with synthetic EUR
  prices (one flagged as a deal with a struck original price for the red-price UI).
  This makes the site fully demoable **before** the agents deploy.
- **Live path** (`DEMO_MODE=0` **and** ARN set): invokes the **AgentCore Runtime**
  via `bedrock-agentcore` `InvokeAgentRuntime`, passing the message + session
  context, and relays the reply. `runtimeSessionId` is normalized to satisfy
  AgentCore's ≥ 33-char rule (a Cognito UUID `sub` passes through; short/anonymous
  ids are deterministically expanded). If the runtime errors mid-deploy, it
  **degrades to the canned reply** (`mode: "demo-fallback"`) so the drawer never
  hangs.

### `agents.py` — roster
Returns the **exact** 8-agent roster (order: orchestrator, weather, then the six
category agents) with verbatim `wid` identities and route chips. Status is
`standby` pre-auth and flips to `running` when called with `?authed=1` (so a reload
after login still shows `running`). These strings are the source of truth the
frontend renders verbatim — they are never invented.

---

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `CATALOG_TABLE` | (shared) | `adidlabs-catalog` table name |
| `BAG_TABLE` | `bag` | `adidlabs-bag` table name (default `adidlabs-bag`) |
| `AGENTCORE_AGENT_ARN` | `chat` | AgentCore Runtime ARN to invoke for `/api/chat` |
| `DEMO_MODE` | `chat` | `1`/`true` forces the canned stylist reply |
| `LITELLM_URL` | (agents/tools) | IAM-auth LiteLLM function URL |
| `KB_ID` | (tools) | Bedrock Knowledge Base id |
| `TAVILY_API_KEY` | (tools) | Optional; enables Tavily for `search_web` |
| `CORS_ALLOW_ORIGIN` | (shared) | Optional; pins the allowed origin (default `*`) |
| `AWS_REGION` | (shared) | Defaults to `ap-southeast-2` |

`LITELLM_URL`, `KB_ID`, and `TAVILY_API_KEY` are consumed by the agent/tool tier
(other modules); they are listed here for the complete contract.

---

## Dependencies

Deliberately minimal (`requirements.txt`):

- **`boto3` / `botocore`** — DynamoDB and AgentCore access (provided by the Lambda
  runtime; pinned for local/CI parity).
- **`tzdata`** — IANA time-zone database for stdlib `zoneinfo`. The Lambda Python
  3.12 image does not bundle it, so without this `session.py` would silently
  resolve `Australia/Sydney` to UTC in production; bundling it makes local, CI, and
  production resolve identical local times. (`session.py` still degrades to UTC
  gracefully if tzdata is ever absent.)
- **`pytest`** — dev/test only.

Open-Meteo and ip-api.com are called with the **standard library** `urllib`, so
there is no `requests` dependency.

---

## Tests

`pytest` unit tests cover a **happy path and an error path for every handler**,
with **zero real network calls**:

- `urllib.request.urlopen` is patched per-test (`tests/conftest.py :: make_urlopen`),
  which asserts on the request URL — any unexpected egress raises `AssertionError`.
  ip-api.com and Open-Meteo are stubbed this way.
- DynamoDB and AgentCore use **botocore `Stubber`**, so no AWS endpoint is reached.
- CORS is asserted on every response (`assert_cors`).
- The chat suite verifies the DEMO_MODE reply is weather-aware and credits the real
  wid roster, that the live path relays the runtime reply, and that a runtime error
  degrades to the canned fallback.

Run:

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest            # 29 tests, ~0.2s, no network
```

---

*Concept demo — no affiliation with adidas AG. All products fictional.*

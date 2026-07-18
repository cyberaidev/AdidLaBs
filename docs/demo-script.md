# AdidLaBs — 5-Minute Demo Script

> **Concept demo — no affiliation with adidas AG. All products fictional.**

A tight, repeatable 5-minute walkthrough that matches the approved v3 mockup flow
(`docs/design.md`). The gating order is mandatory: **RegistrationGate → LoginModal → (authed) →
stylist chat auto-opens + weather bar reveals + agents flip to running.**

**Before you present**
- Run `./deploy.sh` and keep the printed **CloudFront site URL**, **API base URL**, and **LiteLLM
  URL** handy. Stay on the raw CloudFront domain (no custom domain — by design).
- Set `DEMO_MODE=true` on the `api-handler` Lambda so the registration gate accepts any well-formed
  input and agent responses are deterministic. **Never type real credentials or payment details** —
  the gate collects name/email/password only, and checkout is a labelled no-op.
- Have the browser dev console closed and the window sized ≥ 1024px wide (desktop layout).
- Total time budget: **5:00**. Beats below sum to it.

---

## Beat 1 — The wordmark & the pitch (0:00 → 0:30)

- Load the site. Point at the header wordmark: **ADID·*L*·A·*B*·S**, the amber serif-italic **L**
  and **B** are the "lab" highlight — rendered as styled text, no image, fully themeable.
- One-liner: *"AdidLaBs dresses you for the sky. It reads your location and 3-day forecast, then a
  mesh of agents on Amazon Bedrock AgentCore styles a weather-matched outfit — all in
  ap-southeast-2, all near-zero cost when idle."*
- Note the silver hero, square corners, and the **SHOP NOW** button's 3px hard offset shadow (press
  it: it tucks into its own shadow).

## Beat 2 — The gate: join the lab (0:30 → 1:15)

- Scroll to the black **weather bar** — it's **locked**:
  `WEATHER LAB LOCKED — JOIN THE LAB TO SEE YOUR 3-DAY FORECAST`. Location is hidden until auth.
- Click the **user icon** → the **RegistrationGate** modal ("JOIN THE LAB") appears and blocks the
  experience. Fill NAME / EMAIL / PASSWORD (any well-formed values in `DEMO_MODE`). Emphasize: *no
  payment, no sensitive IDs — ever.* Click **CREATE LAB ACCOUNT**.
- The **LoginModal** ("LOG IN") follows. Enter email/password, click **ENTER THE LAB**.
- Talking point: in production this is **Cognito as the AgentCore Identity IdP**, issuing a JWT the
  API Gateway authorizer validates; `user_id` always comes from the token `sub`, never the request
  body.

## Beat 3 — Unlock: weather, location, agents wake up (1:15 → 2:00)

- On login, three things happen at once:
  1. The **stylist chat drawer auto-opens** from the right with the orchestrator's seed line
     *"Reading your 3-day forecast…"*.
  2. The **weather bar reveals** real content from `GET /api/session` + `GET /api/weather`:
     `📍 {city}, {region}` · `{localTime} {tz}` · three day chips with emoji + hi/lo. Location is
     **IP-based** (Open-Meteo, free/keyless) — you never typed a city.
  3. Scroll to **AGENTS ON BEDROCK AGENTCORE**: the 8-card roster flips from **STANDBY** to
     **RUNNING** progressively (orchestrator + weather first, then the six category agents).
- Point at the **workload identity ids** on the cards — e.g. `adidlabs/orchestrator-9f21`,
  `adidlabs/weather-3b7c` — and the model-route chips: **NOVA-PRO** on the orchestrator only,
  **HAIKU-4.5** on every other agent. These are rendered verbatim from `GET /api/agents`.

## Beat 4 — The styling turn: agents fan out (2:00 → 3:30)

- In the chat composer, type a prompt and hit **SEND**, e.g.:
  *"Style me for the next three days — I bike to work and it looks like rain Thursday."*
- Narrate the flow as bubbles appear (`POST /api/chat`):
  1. **`api-handler`** calls `InvokeAgentRuntime` on the AgentCore Runtime (LangGraph orchestrator,
     `AGENTCORE_AGENT_ARN`).
  2. The **weather agent** (Haiku 4.5) normalizes the Open-Meteo forecast into a conditions object.
  3. The **orchestrator** (Nova Pro — the reserved reasoning route) decides which categories matter
     and **fans out over A2A** to the category agents in parallel.
  4. Each category agent calls **MCP tools** on the AgentCore Gateway: `get_catalog` / `get_deals`
     for structured price/stock, and `search_lab_knowledge` (Bedrock KB retrieve) for fabric/care
     and weather-to-outfit rationale — with `search_web` as the KB-miss fallback.
  5. The orchestrator composes one coherent outfit + rationale and returns it.
- Watch the **"agents thinking" row** of 8 status squares light green as each responds. Note agent
  attribution above each bubble, e.g. `SHOES · adidlabs/shoes-4e2a`.
- Point out a **deal** on a returned card: struck original in gray + deal price in red + a `-{pct}%`
  tag (synthetic EUR prices from the mock catalog).

## Beat 5 — Bag, architecture, and the cost story (3:30 → 4:30)

- Click **ADD TO BAG** on a pick, then open the **bag drawer** (bag icon): thumbnail, title,
  `€price`, qty, remove. Subtotal updates. **CHECKOUT (DEMO)** is a deliberate no-op — no payment
  processing. (Optionally show the **wishlist** heart toggle and move-to-bag.)
- Click the **cloud icon** → **ArchitectureDrawer**: CloudFront + S3 → API Gateway + Lambda →
  DynamoDB → AgentCore Runtime + Gateway → LiteLLM on Lambda → Bedrock KB over S3 Vectors, labelled
  **ap-southeast-2 (Sydney)**.
- Close with the money line: *"Nothing here runs a clock. No OpenSearch, no Fargate, no idle
  compute — S3 Vectors instead of a ~$90/mo OpenSearch floor, LiteLLM on Lambda instead of Fargate,
  on-demand DynamoDB. Idle cost is a few cents a month; the real spend is per-request model
  tokens."* (See `docs/cost.md`.)

## Beat 6 — Wrap & disclaimer (4:30 → 5:00)

- Scroll to the footer: the wordmark in white-on-black, the build line
  `Built on AWS Bedrock AgentCore · ap-southeast-2 (Sydney)`, the HF data attribution, the MIT ©
  cyberaidev license line, and the standing disclaimer.
- Say it out loud to close: *"This is a concept demo — no affiliation with adidas AG, all products
  fictional. Everything you saw is open source under MIT at github.com/cyberaidev/AdidLaBs."*

---

## Reset for the next run
- Log out / clear the browser's registered+authed state (the app treats a fresh session as
  unregistered → the gate returns). No backend reset is needed for repeat demos.
- If you want a clean data slate, re-run the seed step (`./deploy.sh` is idempotent on seeding) or
  just leave the demo catalog as-is.

## Fallback talking points (if something is slow or offline)
- **HuggingFace unreachable during seeding:** the catalog falls back to
  `data/synthetic_fallback.json` (~40 items) — the demo still works end to end.
- **S3 Vectors preview hiccup:** `search_lab_knowledge` keeps the same signature via the
  **FAISS-in-Lambda fallback** (`docs/architecture.md` §3.2) — no always-on infra involved.
- **Web search:** defaults to free **ddgs/DuckDuckGo**; if `TAVILY_API_KEY` is set, it uses Tavily.
- **Model latency:** Haiku 4.5 category agents are fast/cheap; only the single Nova Pro orchestrator
  call per turn does heavier reasoning — a brief pause there is expected.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*

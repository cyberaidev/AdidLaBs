# AdidLaBs — Frontend

> **Concept demo — no affiliation with adidas AG. All products fictional.**

Vite + React single-page storefront for AdidLaBs, a weather-matched AI shopping demo on Amazon Bedrock AgentCore (region `ap-southeast-2`, Sydney). This module implements [`docs/design.md`](../docs/design.md) faithfully and consumes the `/api/*` contracts defined in [`docs/architecture.md`](../docs/architecture.md).

## Stack

- **Node ≥ 20**, **Vite 5**, **React 18**.
- Dependencies are intentionally minimal: `react`, `react-dom`, and `amazon-cognito-identity-js` only. No CSS framework, no icon font, no state library — everything is plain React + a single `styles.css`.
- Brand fonts (Anton, Oswald, DM Serif Display italic) load from Google Fonts. Product tile images are inline SVG data URIs — the build has **zero external image dependencies**.

## Quick start

```bash
cd frontend
cp .env.example .env.local   # fill in after deploy; optional for local demo
npm install
npm run dev                  # http://localhost:5173
```

Build the static site (the artifact CloudFront/S3 serves):

```bash
npm run build                # outputs to frontend/dist
npm run preview              # serve the production build locally
```

`npm install && npm run build` completes with zero errors even with no `.env` file present.

## Environment variables

Set these in `.env.local` (see [`.env.example`](./.env.example)). Vite only exposes vars prefixed with `VITE_`.

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Base URL of the API Gateway HTTP API (no trailing slash). All `/api/*` calls target this. |
| `VITE_USER_POOL_ID` | Cognito User Pool id (AgentCore Identity IdP), `ap-southeast-2`. |
| `VITE_USER_POOL_CLIENT_ID` | Cognito App Client id (public SPA client, no secret). |

**Demo mode:** when the Cognito vars are absent the registration/login flow runs locally — any well-formed input registers and logs in with a synthetic token, so the full gated experience (chat auto-open, weather bar, agents flip to running) works before any backend exists. No payment or sensitive IDs are ever collected in the browser.

## Gating flow (mandatory order)

`RegistrationGate → LoginModal → (authed)`

On the very first render the **JOIN THE LAB** gate blocks the page and cannot be dismissed until registration completes. After registration the **LOG IN** modal appears. On successful login the app:

1. auto-opens the **stylist chat** drawer,
2. reveals the black **weather bar** (location from `GET /api/session`, 3-day forecast from `GET /api/weather`),
3. flips the **agents panel** from `standby` → `running` (orchestrator + weather first, then the six category agents).

Before auth the weather bar shows a locked placeholder and location stays hidden.

## API contracts consumed

All calls go to `VITE_API_URL` with the Cognito Bearer JWT attached when available (`src/api.js`). Every call degrades gracefully to a static fallback so the SPA renders pre-deploy.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/session` | server time + IP geolocation |
| GET | `/api/weather` | 3-day forecast (Open-Meteo) |
| GET / POST / DELETE | `/api/bag` | bag read / add / remove |
| POST | `/api/chat` | stylist chat turn (orchestrator → agents) |
| GET | `/api/agents` | agent roster + wid identities + status (static roster fallback) |

These are the exact five route groups defined in `docs/design.md` §7.1 — there is **no** `/api/catalog` endpoint. The **product rail** (`PICKED FOR YOUR FORECAST`) is seeded from the catalog/deals the agents surface via `GET /api/agents` (`docs/design.md` :210), and falls back to a static forecast set (`src/data/fallbackCatalog.js`) when the backend is unreachable or surfaces no recommendations.

The agent roster (names, workload-identity ids, model-route chips) is rendered **verbatim** from the contract and matches `docs/design.md` §5.10. If `/api/agents` is unreachable the panel falls back to the same static roster.

## Structure

```
frontend/
├── index.html                 # entry, Google Fonts preconnect
├── vite.config.js
├── .env.example
├── src/
│   ├── main.jsx               # React root
│   ├── App.jsx                # state + gating + drawers wiring
│   ├── api.js                 # /api/* client (Bearer JWT, graceful fallbacks)
│   ├── auth.js                # Cognito wrapper (+ demo mode)
│   ├── copy.js                # centralized copy deck (design.md §6)
│   ├── styles.css             # all design tokens + component styles
│   ├── data/fallbackCatalog.js
│   └── components/            # one file per component (design.md §4)
└── README.md
```

## Brand & trademark guardrails

Square corners everywhere, Anton/Oswald/DM Serif Display italic only, amber L/B in the `<Wordmark>`, 3px hard offset shadows, red for deals/OUTLET. **No adidas trademarks** — no three stripes, no trefoil, no adidas product names or imagery. The no-affiliation disclaimer is present in the footer and every public-facing doc.

## License

MIT © cyberaidev · [github.com/cyberaidev/AdidLaBs](https://github.com/cyberaidev/AdidLaBs)

Mock data: HuggingFace `ashraq/fashion-product-images-small` (metadata only), synthetic prices.

---
*Concept demo — no affiliation with adidas AG. All products fictional.*

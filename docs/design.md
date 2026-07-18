# AdidLaBs — Brand & UI Design Specification (v3)

> **Concept demo — no affiliation with adidas AG. All products fictional.**

This document is the single source of truth for the frontend creator. It encodes the **approved v3 mockup**: an adidas.com-style layout *language* with **zero adidas trademarks** (no three stripes, no trefoil, no adidas product names or imagery). Implement it exactly. Where a value is specified (hex, px, string), use it verbatim.

- **Stack:** Node >= 20 + Vite + React. Square corners everywhere. No rounded corners, no gradients except the specified silver hero.
- **Region context (display/config only):** ap-southeast-2 (Sydney). Models via LiteLLM routes only (`nova-pro` for orchestrator, `haiku-4.5` for all other agents).
- **Fonts (Google Fonts):** Anton (hero/wordmark display), Oswald (condensed UI/nav/labels), DM Serif Display *italic* (the serif amber accent letters).

---

## 1. Brand Foundations

### 1.1 Wordmark — `ADID L A B S`

The wordmark is the load-bearing brand device. It is **not** an image; render it as styled text so it stays crisp and themeable.

Letter-by-letter composition (left to right, no spaces between letters):

| Segment | Glyphs | Font | Style | Color token |
|---|---|---|---|---|
| 1 | `ADID` | Anton | uppercase, normal | `--ink` (#0A0A0A) |
| 2 | `L` | DM Serif Display | **italic** | `--amber` (#E8A200) |
| 3 | `A` | Anton | uppercase, normal | `--ink` |
| 4 | `B` | DM Serif Display | **italic** | `--amber` |
| 5 | `S` | Anton | uppercase, normal | `--ink` |

- Reads as **ADID*L*A*B*S** — the *L* and *B* are the amber serif-italic "lab" highlight.
- The serif italic letters sit on the same baseline; optical size tuned so `L` and `B` cap-heights match the Anton caps (set DM Serif Display ~1.02em relative to Anton, `font-style: italic`).
- Kerning: letter-spacing `-0.01em` on the Anton segments; serif letters get `0` and a `2px` left/right optical margin so they don't collide.
- Minimum render size: 20px cap height. Never distort, outline, or add a mark/emblem inside the wordmark.
- On dark backgrounds (footer), swap `--ink` glyphs to `--paper` (#FFFFFF); amber stays `--amber`.

React implementation contract:

```jsx
// components/Wordmark.jsx — inline spans, no <img>
export function Wordmark({ className }) {
  return (
    <span className={`adidlabs-wordmark ${className ?? ""}`} aria-label="AdidLaBs">
      <span className="wm-anton">ADID</span>
      <span className="wm-serif">L</span>
      <span className="wm-anton">A</span>
      <span className="wm-serif">B</span>
      <span className="wm-anton">S</span>
    </span>
  );
}
```

```css
.adidlabs-wordmark { display:inline-flex; align-items:baseline; line-height:1; }
.wm-anton { font-family:"Anton",sans-serif; color:var(--ink); letter-spacing:-0.01em; text-transform:uppercase; }
.wm-serif { font-family:"DM Serif Display",serif; font-style:italic; color:var(--amber); font-size:1.02em; margin:0 2px; }
.on-dark .wm-anton { color:var(--paper); }
```

### 1.2 Type system

| Role | Family | Weight/Style | Case | Use |
|---|---|---|---|---|
| Hero display | Anton | 400 | UPPERCASE | Hero headline, huge numerals |
| Section display | Oswald | 600–700 | UPPERCASE | Section titles, rail heading, buttons |
| Nav / labels | Oswald | 500 | UPPERCASE | Nav items, chips, weather bar, tags |
| Body / UI | Oswald | 300–400 | Sentence | Paragraphs, chat, form fields, prices |
| Serif accent | DM Serif Display | italic | as-is | Wordmark `L`/`B` only (do not use elsewhere) |

- Load via one Google Fonts link (preconnect + `display=swap`):
  `https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@300;400;500;600;700&family=DM+Serif+Display:ital@1&display=swap`
- Base body size 16px; line-height 1.5 for body, 1.0 for display.

### 1.3 Layout language (adidas.com-inspired, trademark-free)

- Full-bleed sections stacked vertically; content max-width 1280px, gutter 24px (16px on mobile).
- **Square corners on every element** (`border-radius: 0`). Global reset enforces it.
- Hard edges: borders are 1px or 2px solid; the SHOP NOW button and product hearts use a **3px hard offset shadow** (no blur).
- Uppercase condensed nav, centered.
- High-contrast black/white with amber as the single accent and red reserved for deals/outlet.
- No adidas assets: no three-stripe motif, no trefoil, no product names (e.g. no "Ultraboost"/"Samba"/"Gazelle"), no adidas photography. Product imagery is fictional/synthetic only.

---

## 2. Color Tokens

Define all as CSS custom properties on `:root`. Hex is authoritative.

| Token | Hex | Role |
|---|---|---|
| `--ink` | `#0A0A0A` | Primary black — text, nav, weather bar, footer, borders |
| `--paper` | `#FFFFFF` | White — page bg, label boxes, button faces |
| `--amber` | `#E8A200` | Brand accent — wordmark L/B, active nav underline, focus, chat accents |
| `--amber-deep` | `#B87E00` | Amber pressed/hover state |
| `--silver-1` | `#E9EBEE` | Hero silver gradient top |
| `--silver-2` | `#C7CCD2` | Hero silver gradient mid |
| `--silver-3` | `#AAB0B8` | Hero silver gradient bottom |
| `--tile` | `#F4F4F5` | Product tile background (light gray) |
| `--tile-line` | `#E3E3E5` | Tile / hairline borders |
| `--muted` | `#6B7076` | Secondary text, meta, timestamps |
| `--deal-red` | `#D0021B` | Deal/sale prices, OUTLET nav item, discount tags |
| `--strike` | `#9A9DA2` | Struck-through original price |
| `--ok-green` | `#1E8E3E` | "running" agent status dot |
| `--standby` | `#9A9DA2` | "standby" agent status dot |
| `--shadow` | `#0A0A0A` | Hard offset shadow color (used at 100%, no blur) |
| `--overlay` | `rgba(10,10,10,0.62)` | Modal scrim |
| `--chip-bg` | `#111214` | Model route chip background |
| `--chip-text` | `#F4F4F5` | Model route chip text |

Hard shadow utility (reused by button + hearts + agent cards):

```css
--hard-shadow: 3px 3px 0 0 var(--shadow); /* 3px offset, 0 blur, 0 spread */
```

---

## 3. Spacing, Grid & Elevation

- **Spacing scale (px):** 4, 8, 12, 16, 24, 32, 48, 64, 96. Use tokens `--s1..--s9`.
- **Grid:** 12-col, 24px gutter, max 1280px. Product rail = 4 columns desktop / 2 tablet / 1 mobile.
- **Breakpoints:** mobile < 640, tablet 640–1023, desktop >= 1024.
- **Borders:** hairlines 1px `--tile-line`; structural 2px `--ink`.
- **Elevation:** only two kinds —
  1. Hard offset (`--hard-shadow`) for interactive boxes (button, hearts, agent cards, label boxes on hover).
  2. Modal scrim `--overlay` for the registration/login/chat layers.
  - No soft/blurred drop shadows anywhere.
- **Focus ring:** `outline: 3px solid var(--amber); outline-offset: 2px;` on all focusable elements.

---

## 4. Component Inventory

Ordered top-to-bottom as they appear. Each maps to a React component under `src/components/`.

| # | Component | File | Notes |
|---|---|---|---|
| 1 | `TopUtilityBar` | `TopUtilityBar.jsx` | thin black strip, tagline + right meta |
| 2 | `Header` | `Header.jsx` | wordmark left, centered nav, corner icons right |
| 3 | `CornerIcons` | `CornerIcons.jsx` | cloud(architecture)/user/heart(wishlist)/bag |
| 4 | `NavBar` | `NavBar.jsx` | centered uppercase condensed nav |
| 5 | `HeroBanner` | `HeroBanner.jsx` | silver gradient, ADIDLABS/FORECAST COLLECTION, label boxes, SHOP NOW |
| 6 | `WeatherBar` | `WeatherBar.jsx` | black bar: location · time · 3-day (gated) |
| 7 | `ProductRail` | `ProductRail.jsx` | PICKED FOR YOUR FORECAST, 4-up tiles |
| 8 | `ProductCard` | `ProductCard.jsx` | tile, heart, price/deal price, category tag |
| 9 | `AgentsPanel` | `AgentsPanel.jsx` | Agents on Bedrock AgentCore roster |
| 10 | `AgentCard` | `AgentCard.jsx` | name, wid, model chip, status dot |
| 11 | `RegistrationGate` | `RegistrationGate.jsx` | JOIN THE LAB modal (precedes login) |
| 12 | `LoginModal` | `LoginModal.jsx` | shown after registration |
| 13 | `StylistChat` | `StylistChat.jsx` | right drawer, auto-opens post-login |
| 14 | `ArchitectureDrawer` | `ArchitectureDrawer.jsx` | toggled by cloud icon |
| 15 | `WishlistDrawer` | `WishlistDrawer.jsx` | toggled by heart icon |
| 16 | `BagDrawer` | `BagDrawer.jsx` | toggled by bag icon |
| 17 | `Footer` | `Footer.jsx` | black footer + no-affiliation disclaimer |
| 18 | `Wordmark` | `Wordmark.jsx` | shared brand text (Section 1.1) |

---

## 5. Component Specs

### 5.1 TopUtilityBar
- Full-bleed, bg `--ink`, text `--paper`, Oswald 500, 12px, uppercase, height 34px, centered vertical.
- Left: `FREE SHIPPING ON THE FORECAST` · Right: `HELP` `RETURNS` `AU $` (Oswald 12px, `--muted` on hover to `--paper`).
- Purely decorative demo copy; no functional links required.

### 5.2 Header
- Height 72px, bg `--paper`, bottom 2px `--ink` border. Sticky at top (`position: sticky; top: 0; z-index: 40`).
- Left: `<Wordmark>` at 30px cap height, vertically centered, 24px left gutter.
- Center: `<NavBar>` (absolutely centered on desktop; hamburger on mobile).
- Right: `<CornerIcons>`.

### 5.3 CornerIcons (top-right, in this exact order, left→right)
1. **Cloud** — architecture icon → toggles `ArchitectureDrawer`. aria-label `AWS architecture`.
2. **User** — profile / auth state → opens `LoginModal` (or registration gate if not registered). aria-label `Account`.
3. **Heart** — wishlist → toggles `WishlistDrawer`, shows count badge. aria-label `Wishlist`.
4. **Bag** — cart → toggles `BagDrawer`, shows count badge. aria-label `Bag`.
- 24px line icons, `--ink`, 20px gap, amber on hover/active. Count badges: 16px square, bg `--amber`, `--ink` text, Oswald 700 10px, square corners.
- Use inline SVG stroke icons (stroke 2px). No icon font.

### 5.4 NavBar
- Oswald 600, 14px, uppercase, letter-spacing 0.06em, `--ink`, 28px item gap, centered.
- Items in order: `SHOES`, `MEN`, `WOMEN`, `KIDS`, `WEATHER LAB`, `OUTLET`.
- `OUTLET` renders in `--deal-red`.
- Active/hover: 2px amber underline (`box-shadow: inset 0 -2px 0 var(--amber)` or bottom border), no color change except OUTLET stays red.
- Demo nav is non-routing (single page); items are visual.

### 5.5 HeroBanner (silver hero)
- Full-bleed, min-height 460px (desktop) / 360px (mobile), flex center.
- **Background:** linear silver gradient
  `linear-gradient(180deg, var(--silver-1) 0%, var(--silver-2) 55%, var(--silver-3) 100%)`. No image.
- **Headline** (Anton, `--ink`, uppercase, tight):
  - Line 1: `ADIDLABS` — clamp 64–140px, letter-spacing -0.02em, line-height 0.92.
  - Line 2: `FORECAST COLLECTION` — clamp 40–84px.
  - Note: In the hero headline `ADIDLABS` is set in Anton as a single word (display lockup); the *serif-amber L/B treatment applies to the `<Wordmark>` brand device* (header/footer/chat/modals), **not** to the giant hero word. Keep the hero word monolithic Anther-black for the poster look.
- **White label boxes:** two/three small boxes overlaid near the headline, bg `--paper`, 1px `--ink` border, Oswald 500 11px uppercase, padding 6px 10px, square corners. Copy: `NEW`, `AI STYLED`, `3-DAY FORECAST`. Position: top-left cluster above line 1, 12px gaps.
- **SHOP NOW button** (the signature control):
  - Boxed: bg `--paper`, 2px `--ink` border, `--ink` text, Oswald 700 15px uppercase, padding 14px 28px, label `SHOP NOW`, optional trailing `→`.
  - **3px hard offset shadow:** `box-shadow: var(--hard-shadow);` (`3px 3px 0 0 #0A0A0A`), no blur.
  - Hover: translate(-1px,-1px), shadow grows to `5px 5px 0 0` . Active/press: translate(2px,2px), shadow shrinks to `1px 1px 0 0` (tactile "press into shadow").
  - Square corners. `type=button`; in demo it scrolls to the product rail.

### 5.6 WeatherBar (black weather strip) — GATED
- Full-bleed, bg `--ink`, text `--paper`, height 48px, Oswald 500 13px uppercase, single row, centered, `·` separators.
- Content (populated from `GET /api/session` + `GET /api/weather`): `📍 {city}, {region}` · `{localTime} {tz}` · then three day chips: `{DAY} {emoji} {hi}°/{lo}°`.
- **Gate behavior:** before auth, render a locked placeholder: `WEATHER LAB LOCKED — JOIN THE LAB TO SEE YOUR 3-DAY FORECAST` with a small lock glyph, `--muted` text. After login, fetch and reveal the real location/time/3-day. Location is IP-based (from `/api/session`); never ask the user to type it.
- Day emoji mapping from Open-Meteo weathercode → sun/cloud/rain/snow glyph (documented in `WeatherBar.jsx`).

### 5.7 ProductRail — `PICKED FOR YOUR FORECAST`
- Section heading: Oswald 700, 28px, uppercase, `--ink`, left-aligned, 2px amber underline under the first word width. Sub: `Weather-matched by the stylist agents.` Oswald 300 14px `--muted`.
- 4-up grid on `--paper` page bg; tiles are `--tile`.
- Data source: `GET /api/bag` is separate; rail items come from the catalog/deals surfaced by agents (demo may seed from `/api/agents` recommendations or a static forecast set). Each card = one catalog item.

### 5.8 ProductCard
- Tile bg `--tile`, 1px `--tile-line` border, square corners, padding 0 (image edge-to-edge) with 12px inner text padding.
- **Image area:** 1:1, object-fit cover, fictional/synthetic product image (from mock catalog); on missing image show a neutral `--tile` placeholder with the category name in Oswald 300.
- **Heart (wishlist toggle):** top-right, 28px square white box, 1px `--ink` border, **3px hard offset shadow** (`var(--hard-shadow)`), heart outline `--ink`; when active fill `--deal-red`. Toggling posts to wishlist state.
- **Category tag:** top-left, Oswald 500 10px uppercase, bg `--ink`, text `--paper`, padding 3px 6px. One of: `SHOES PANTS TSHIRT JUMPER JACKET ACCESSORY`.
- **Title:** Oswald 500 15px `--ink`, 2-line clamp.
- **Price block:**
  - Regular: Oswald 600 16px `--ink`, `€{price}`.
  - **Deal:** show struck original in `--strike` (`--strike` color, line-through, 13px) followed by **deal price in `--deal-red`** Oswald 700 16px, plus a red tag `-{pct}%` (bg `--deal-red`, `--paper` text, 10px). Currency is EUR (synthetic prices per mock data).
- **Add to bag:** small boxed button `ADD TO BAG`, `--ink` border, hover amber; POSTs `POST /api/bag`.

### 5.9 AgentsPanel — `AGENTS ON BEDROCK AGENTCORE`
- Section on `--paper`, heading Oswald 700 28px uppercase, amber underline. Sub: `Live roster · region ap-southeast-2 (Sydney).`
- Grid of 8 `AgentCard`s (4-up desktop / 2 tablet / 1 mobile).
- Data from `GET /api/agents` (roster + identities + status). Status transitions `standby → running` after login (orchestrator/weather first, then category agents as the chat fans out).

### 5.10 AgentCard (display the wid identities EXACTLY)
Each card shows: agent name (Oswald 600 16px uppercase), **workload identity id** (`wid`, Oswald 300 12px `--muted`, monospace-ish, verbatim), **model route chip**, and a **status dot**.

- **Model route chip:** small box, bg `--chip-bg`, text `--chip-text`, Oswald 500 10px uppercase, padding 3px 7px, square corners. Value is the LiteLLM route name: `NOVA-PRO` (orchestrator only) or `HAIKU-4.5` (all others).
- **Status dot:** 8px square (not circle), `--ok-green` when `running`, `--standby` when `standby`, with label in Oswald 500 11px.
- Card: `--tile` bg, 1px `--tile-line`, on hover `--hard-shadow`.

**Exact roster (name · wid · route) — render verbatim:**

| Agent | wid (display exactly) | Route chip |
|---|---|---|
| ORCHESTRATOR | `adidlabs/orchestrator-9f21` | `NOVA-PRO` |
| WEATHER | `adidlabs/weather-3b7c` | `HAIKU-4.5` |
| SHOES | `adidlabs/shoes-4e2a` | `HAIKU-4.5` |
| PANTS | `adidlabs/pants-8c1d` | `HAIKU-4.5` |
| TSHIRT | `adidlabs/tshirt-2a9e` | `HAIKU-4.5` |
| JUMPER | `adidlabs/jumper-6d3f` | `HAIKU-4.5` |
| JACKET | `adidlabs/jacket-1e8b` | `HAIKU-4.5` |
| ACCESSORY | `adidlabs/accessory-5c4a` | `HAIKU-4.5` |

Ordering in the grid: orchestrator first, weather second, then shoes, pants, tshirt, jumper, jacket, accessory.

### 5.11 RegistrationGate — `JOIN THE LAB` (precedes login)
- **Flow:** on first visit (no registered flag in state), the gate modal is shown and **blocks the experience**. Registration must complete **before** the `LoginModal`. Only after login do the **stylist chat (auto-opens)**, **weather bar**, and **IP-based location** unlock.
- Modal: centered card on `--overlay` scrim, bg `--paper`, 2px `--ink` border, max-width 440px, square corners, `--hard-shadow`.
- Header: `<Wordmark>` (24px) + title `JOIN THE LAB` (Anton 34px uppercase). Sub: `Register to unlock your weather-matched stylist.` Oswald 300 14px `--muted`.
- Fields (Oswald 400 14px; 1px `--ink` border inputs, square, focus amber ring): `NAME`, `EMAIL`, `PASSWORD` (masked). **Do not** collect payment or sensitive IDs.
- Primary button `CREATE LAB ACCOUNT` — boxed `--ink` bg, `--paper` text, `--hard-shadow`, hover amber.
- Secondary: `Already in the lab? Log in` → switches to `LoginModal`.
- Auth is via Bedrock AgentCore identity (Cognito IdP) in production; in `DEMO_MODE=true` the gate accepts any well-formed input and proceeds (no real credential handling in the browser).
- Accessibility: focus-trapped, `role="dialog"`, `aria-modal="true"`, ESC disabled until registered (it's a gate).

### 5.12 LoginModal
- Same visual system as the gate. Title `LOG IN` (Anton 34px). Fields `EMAIL`, `PASSWORD`. Button `ENTER THE LAB`.
- On success: set authed state → close modals → **auto-open StylistChat**, reveal WeatherBar + location, flip agent statuses to `running`, capture client IP via `/api/session`.
- Link back: `Need an account? Join the lab` → `RegistrationGate`.

### 5.13 StylistChat (right drawer, auto-opens after login)
- Right-side drawer, width 400px (full-width sheet on mobile), bg `--paper`, left 2px `--ink` border, `z-index: 50`. Slides in from right; **auto-opens immediately after successful login.**
- Header: `<Wordmark>` (20px) + `STYLIST` (Oswald 700 16px), close `×`. Amber 3px top accent line.
- Greeting seeded by orchestrator (nova-pro): `Reading your 3-day forecast…` then weather-matched picks.
- Message list: user bubbles right (bg `--ink`, `--paper` text, square), agent bubbles left (bg `--tile`, `--ink` text, square, 3px amber left border). Agent name label above each agent bubble in Oswald 500 11px `--muted` (e.g. `SHOES · adidlabs/shoes-4e2a`).
- Composer: text input (Oswald 400 14px) + `SEND` boxed button (amber). POSTs `POST /api/chat`.
- "Agents thinking" indicator: row of the 8 status squares lighting green as each responds.

### 5.14 ArchitectureDrawer (cloud icon)
- Left or right drawer showing the AWS architecture (static diagram/list), region label `ap-southeast-2 (Sydney)`.
- Lists: CloudFront + S3 (static React) → API Gateway (HTTP API) + Lambda (Python 3.12) → DynamoDB (`adidlabs-catalog`, `adidlabs-bag`, PAY_PER_REQUEST) → Bedrock AgentCore runtime (8 agents) + Gateway (MCP tools) → LiteLLM on Lambda (aws-lambda-web-adapter, IAM-auth function URL) → Bedrock Knowledge Bases over Amazon S3 Vectors (Titan Text v2 embeddings; FAISS-in-Lambda fallback noted).
- Non-interactive demo content; visual only. Square-cornered node boxes, `--ink` borders, amber connectors.

### 5.15 WishlistDrawer / BagDrawer
- Right drawers, same chrome as StylistChat.
- **BagDrawer:** items from `GET /api/bag`; each row = image thumb, title, `€price`, qty, remove (`DELETE /api/bag`). Subtotal in Oswald 700. `CHECKOUT` button is a **demo no-op** (label `CHECKOUT (DEMO)`); do not process payments.
- **WishlistDrawer:** hearted items; move-to-bag posts `POST /api/bag`.

### 5.16 Footer (black)
- Full-bleed, bg `--ink`, text `--paper`, `.on-dark` scope (wordmark glyphs go white, amber L/B stay amber).
- Top row: `<Wordmark>` (26px) + four link columns (Oswald 300 13px): `SHOP` (Shoes/Pants/Tshirt/Jumper/Jacket/Accessory), `LAB` (Weather Lab/Forecast Collection/Deals), `HELP` (Shipping/Returns/Sizing), `ABOUT` (Concept/Tech/GitHub).
- Region + build line: Oswald 300 12px `--muted`: `Built on AWS Bedrock AgentCore · ap-southeast-2 (Sydney)`.
- **Disclaimer (mandatory, verbatim), Oswald 400 12px, `--muted`, always visible:**
  `Concept demo — no affiliation with adidas AG. All products fictional.`
- License line: `MIT © cyberaidev · github.com/cyberaidev/AdidLaBs`.
- Data attribution: `Mock data: HuggingFace ashraq/fashion-product-images-small (metadata only), synthetic prices.`

---

## 6. Copy Deck (all strings)

Centralize in `src/copy.js` so nothing is hard-coded in JSX.

```js
export const COPY = {
  brand: { name: "AdidLaBs" },

  utility: {
    left: "FREE SHIPPING ON THE FORECAST",
    right: ["HELP", "RETURNS", "AU $"],
  },

  nav: ["SHOES", "MEN", "WOMEN", "KIDS", "WEATHER LAB", "OUTLET"],
  navRedItem: "OUTLET",

  hero: {
    line1: "ADIDLABS",
    line2: "FORECAST COLLECTION",
    labelBoxes: ["NEW", "AI STYLED", "3-DAY FORECAST"],
    cta: "SHOP NOW",
    ctaArrow: "→",
  },

  weatherBar: {
    lockedText: "WEATHER LAB LOCKED — JOIN THE LAB TO SEE YOUR 3-DAY FORECAST",
    // runtime: `📍 ${city}, ${region}` · `${localTime} ${tz}` · day chips
  },

  rail: {
    heading: "PICKED FOR YOUR FORECAST",
    sub: "Weather-matched by the stylist agents.",
    addToBag: "ADD TO BAG",
  },

  agentsPanel: {
    heading: "AGENTS ON BEDROCK AGENTCORE",
    sub: "Live roster · region ap-southeast-2 (Sydney).",
    statusRunning: "RUNNING",
    statusStandby: "STANDBY",
  },

  gate: {
    title: "JOIN THE LAB",
    sub: "Register to unlock your weather-matched stylist.",
    fields: { name: "NAME", email: "EMAIL", password: "PASSWORD" },
    primary: "CREATE LAB ACCOUNT",
    secondary: "Already in the lab? Log in",
  },

  login: {
    title: "LOG IN",
    fields: { email: "EMAIL", password: "PASSWORD" },
    primary: "ENTER THE LAB",
    secondary: "Need an account? Join the lab",
  },

  chat: {
    title: "STYLIST",
    seed: "Reading your 3-day forecast…",
    placeholder: "Ask the stylist…",
    send: "SEND",
  },

  architecture: {
    title: "ARCHITECTURE",
    region: "ap-southeast-2 (Sydney)",
  },

  bag: { title: "BAG", subtotal: "SUBTOTAL", checkout: "CHECKOUT (DEMO)", empty: "Your bag is empty." },
  wishlist: { title: "WISHLIST", moveToBag: "MOVE TO BAG", empty: "No saved items yet." },

  footer: {
    columns: {
      SHOP: ["Shoes", "Pants", "Tshirt", "Jumper", "Jacket", "Accessory"],
      LAB: ["Weather Lab", "Forecast Collection", "Deals"],
      HELP: ["Shipping", "Returns", "Sizing"],
      ABOUT: ["Concept", "Tech", "GitHub"],
    },
    buildLine: "Built on AWS Bedrock AgentCore · ap-southeast-2 (Sydney)",
    disclaimer: "Concept demo — no affiliation with adidas AG. All products fictional.",
    license: "MIT © cyberaidev · github.com/cyberaidev/AdidLaBs",
    dataAttribution: "Mock data: HuggingFace ashraq/fashion-product-images-small (metadata only), synthetic prices.",
  },

  agents: [
    { name: "ORCHESTRATOR", wid: "adidlabs/orchestrator-9f21", route: "NOVA-PRO" },
    { name: "WEATHER",      wid: "adidlabs/weather-3b7c",      route: "HAIKU-4.5" },
    { name: "SHOES",        wid: "adidlabs/shoes-4e2a",        route: "HAIKU-4.5" },
    { name: "PANTS",        wid: "adidlabs/pants-8c1d",        route: "HAIKU-4.5" },
    { name: "TSHIRT",       wid: "adidlabs/tshirt-2a9e",       route: "HAIKU-4.5" },
    { name: "JUMPER",       wid: "adidlabs/jumper-6d3f",       route: "HAIKU-4.5" },
    { name: "JACKET",       wid: "adidlabs/jacket-1e8b",       route: "HAIKU-4.5" },
    { name: "ACCESSORY",    wid: "adidlabs/accessory-5c4a",    route: "HAIKU-4.5" },
  ],
};
```

---

## 7. State & Flow (frontend contract)

Gating order is mandatory: **RegistrationGate → LoginModal → (authed) → auto-open StylistChat + reveal WeatherBar/location + agents flip to running.**

```
appState = {
  registered: boolean,   // set true by RegistrationGate
  authed: boolean,       // set true by LoginModal
  session: null | { city, region, ip, localTime, tz },   // GET /api/session (post-auth)
  weather: null | [3 days],                              // GET /api/weather (post-auth)
  bag: [], wishlist: [],
  agents: [ ...roster with status ],                     // GET /api/agents
  drawers: { chat:false, arch:false, wishlist:false, bag:false },
}
```

- On mount: if `!registered` → show `RegistrationGate` (blocking). Weather bar shows locked placeholder; location hidden.
- On register success → `registered=true`, show `LoginModal`.
- On login success → `authed=true`; call `GET /api/session`, `GET /api/weather`, `GET /api/agents`; open chat drawer; flip agent statuses to `running` progressively.
- Icons: cloud→arch drawer, user→login/account, heart→wishlist drawer, bag→bag drawer (mutually exclusive open on mobile).

### 7.1 API endpoints consumed (HTTP API)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/session` | time + IP geolocation (post-auth) |
| GET | `/api/weather` | 3-day forecast (Open-Meteo, no key) |
| GET/POST/DELETE | `/api/bag` | bag read / add / remove |
| POST | `/api/chat` | stylist chat turn (orchestrator → agents) |
| GET | `/api/agents` | agent roster + wid identities + status |

---

## 8. Accessibility & Quality Bar
- Color contrast: body text vs bg >= 4.5:1; amber on white used for large/graphic elements or with `--ink` text, not as small body text on white.
- All modals/drawers: `role="dialog"`, `aria-modal`, focus trap, labelled by title. RegistrationGate cannot be dismissed until registered.
- Icons have `aria-label`s (Section 5.3). Status dots have text labels (`RUNNING`/`STANDBY`), not color alone.
- Keyboard: all interactive controls tabbable; amber focus ring (Section 3). SHOP NOW and hearts operable by Enter/Space.
- Respect `prefers-reduced-motion`: disable drawer slide + button translate.

## 9. Do / Don't (trademark & brand guardrails)
- **Do:** square corners; Anton/Oswald/DM Serif Display italic only; amber L/B in the `<Wordmark>`; 3px hard offset shadows; red for deals/OUTLET; the exact wid identities and route chips; the disclaimer on every public surface.
- **Don't:** three stripes, trefoil, any adidas product name/photo/logo; rounded corners; blurred shadows; a custom domain (stay on the raw CloudFront URL); collecting payment/sensitive IDs in the browser; inventing wid ids or model routes.

---
*Concept demo — no affiliation with adidas AG. All products fictional.*

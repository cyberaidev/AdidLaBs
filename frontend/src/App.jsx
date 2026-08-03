import { useCallback, useEffect, useRef, useState } from "react";
import { COPY } from "./copy.js";
import {
  getSession,
  getWeather,
  getAgents,
  getForecastRail,
  getBag,
  getCatalog,
  addToBag,
  removeFromBag,
  postChat,
} from "./api.js";
import { imageForItem } from "./data/productImages.js";
import { FALLBACK_CATALOG } from "./data/fallbackCatalog.js";

// Deals-first, category-balanced sample of the live catalog for the rail:
// two picks per category (discounted items first) keeps every section
// represented with real product photography.
function railSample(items, perCategory = 2) {
  const byCat = new Map();
  const sorted = [...items].sort((a, b) => {
    const aDeal = a.deal_price != null && a.deal_price < a.price ? 0 : 1;
    const bDeal = b.deal_price != null && b.deal_price < b.price ? 0 : 1;
    return aDeal - bDeal;
  });
  for (const it of sorted) {
    const cat = String(it.category || "").toUpperCase();
    const bucket = byCat.get(cat) || [];
    if (bucket.length < perCategory) {
      bucket.push(it);
      byCat.set(cat, bucket);
    }
  }
  return CATEGORY_ORDER.flatMap((c) => byCat.get(c) || []);
}

import { TopUtilityBar } from "./components/TopUtilityBar.jsx";
import { Header } from "./components/Header.jsx";
import { HeroBanner } from "./components/HeroBanner.jsx";
import { WeatherBar } from "./components/WeatherBar.jsx";
import { ProductRail } from "./components/ProductRail.jsx";
import { AgentsPanel } from "./components/AgentsPanel.jsx";
import { Footer } from "./components/Footer.jsx";
import { RegistrationGate } from "./components/RegistrationGate.jsx";
import { LoginModal } from "./components/LoginModal.jsx";
import { StylistChat } from "./components/StylistChat.jsx";
import { ArchitectureDrawer } from "./components/ArchitectureDrawer.jsx";
import { BagDrawer } from "./components/BagDrawer.jsx";
import { WishlistDrawer } from "./components/WishlistDrawer.jsx";
import { TerminalDrawer } from "./components/TerminalDrawer.jsx";
import { LiteLLMPanel } from "./components/LiteLLMPanel.jsx";
import { AccountDrawer } from "./components/AccountDrawer.jsx";
import { CategoryDrawer } from "./components/CategoryDrawer.jsx";
import { StatsStrip, FeatureCards, AgentBanner } from "./components/HdrSections.jsx";

// Decode a JWT payload (base64url) for display-only claims (email, sub).
function parseJwt(token) {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
}

// Map an orchestrator pick to the SPA item shape, tagged with its AI
// provenance label. Picks arrive in two dialects: DynamoDB rows
// (name/original_price/price/discount_pct) or the agents' local seed
// (title/price/deal_pct) — handle both so AI rows never price at $0.
function pickToRow(pick, index, label) {
  const category = String(pick.category || "pick").toUpperCase();
  const title = pick.title || pick.name || `Forecast pick ${index + 1}`;
  const base = Number(
    pick.original_price ?? pick.price ?? pick.price_usd ?? pick.price_eur ?? 0
  );
  const pct = Number(pick.discount_pct ?? pick.deal_pct ?? 0);
  const current = Number(pick.price ?? base) || base;
  let price = base;
  let dealPrice = null;
  if (current > 0 && current < base) {
    dealPrice = current;
  } else if (pct > 0 && base > 0) {
    dealPrice = Math.round(base * (1 - pct / 100) * 100) / 100;
  }
  const item_id = pick.item_id || `ai-${category.toLowerCase()}-${index + 1}`;
  return {
    item_id,
    title,
    category,
    price,
    deal_price: dealPrice,
    image: imageForItem({ ...pick, item_id, category }),
    image_url: pick.image_url || null,
    ai_pick: true,
    ai_note: label,
  };
}

// Roster with standby status, used until GET /api/agents responds (or as fallback).
const STANDBY_ROSTER = COPY.agents.map((a) => ({ ...a, status: "standby" }));

// Category agents flip to running after orchestrator + weather (§5.9).
const CATEGORY_ORDER = ["SHOES", "PANTS", "TSHIRT", "JUMPER", "JACKET", "ACCESSORY"];

export default function App() {
  // Auth state (§7 rev.): the storefront is fully browsable anonymously —
  // the register/login popup appears only when the visitor clicks an
  // account-gated action (Account, Bag, add-to-bag, Stylist, terminal).
  const [authed, setAuthed] = useState(false);
  const [authPopup, setAuthPopup] = useState(null); // null | 'register' | 'login'
  const [pendingEmail, setPendingEmail] = useState("");
  const [token, setToken] = useState(null);
  // The action the visitor was attempting when the popup opened; replayed
  // right after a successful login.
  const pendingIntentRef = useRef(null); // { type: 'drawer'|'add', ... } | null

  // Data state.
  const [session, setSession] = useState(null);
  const [weather, setWeather] = useState(null);
  const [agents, setAgents] = useState(STANDBY_ROSTER);
  const [catalog, setCatalog] = useState([]);
  const [bag, setBag] = useState([]);
  const [wishlist, setWishlist] = useState([]);

  // Mutually-exclusive drawers (§7).
  const [drawer, setDrawer] = useState(null); // 'chat' | 'arch' | 'wishlist' | 'bag' | 'terminal' | null
  const [terminalAgent, setTerminalAgent] = useState(null); // roster entry or null (= all sessions)
  const [browseCategory, setBrowseCategory] = useState(null); // 'SHOES' … for the browse drawer
  const [userEmail, setUserEmail] = useState("");

  // Chat history lives here (not in the drawer) so closing and reopening the
  // stylist keeps the whole conversation for the session.
  const [chatMessages, setChatMessages] = useState([
    {
      role: "agent",
      agent: "ORCHESTRATOR",
      wid: "adidlabs/orchestrator-9f21",
      text: COPY.chat.seed,
    },
  ]);
  const aiKitRef = useRef(false);
  const bagRef = useRef([]);
  const fullCatalogRef = useRef(null);

  useEffect(() => {
    bagRef.current = bag;
  }, [bag]);

  // Full catalog (all categories), fetched once and cached — used to resolve
  // chat asks that name a specific product ("add Aurora Black Belt").
  async function ensureFullCatalog() {
    if (fullCatalogRef.current) return fullCatalogRef.current;
    const data = await getCatalog(null, 200);
    fullCatalogRef.current = data?.items || [];
    return fullCatalogRef.current;
  }

  const railRef = useRef(null);
  const flipTimers = useRef([]);

  // Product-rail items load immediately. Preference order: catalog/deals the
  // agents surfaced (GET /api/agents) → a deals-first, category-balanced sample
  // of the real DynamoDB catalog (GET /api/catalog) → the static fallback set
  // (pre-deploy / offline only).
  useEffect(() => {
    let alive = true;
    (async () => {
      const [agentRail, cat] = await Promise.all([
        getForecastRail(null),
        getCatalog(null, 200).catch(() => null),
      ]);
      if (!alive) return;
      if (Array.isArray(agentRail) && agentRail.length) {
        setCatalog(agentRail);
      } else {
        const items = cat?.items || [];
        setCatalog(items.length ? railSample(items) : FALLBACK_CATALOG);
        if (items.length) fullCatalogRef.current = items;
      }
    })();
    return () => {
      alive = false;
      flipTimers.current.forEach(clearTimeout);
    };
  }, []);

  // Anonymous bootstrap — /api/session, /api/weather and /api/agents are
  // public routes, so time/location, the live 3-day forecast, and the agent
  // roster all render before any login. Agents stay STANDBY until auth.
  useEffect(() => {
    let alive = true;
    (async () => {
      const [sess, wx, roster] = await Promise.all([
        getSession(null),
        getWeather(null),
        getAgents(null),
      ]);
      if (!alive) return;
      if (sess) setSession(sess);
      if (wx) setWeather(Array.isArray(wx) ? wx : wx.days || wx.forecast || null);
      if (roster && roster.length) {
        setAgents(roster.map((a) => ({ ...a, status: "standby" })));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Progressively flip agent statuses standby → running after login.
  const startAgentFlip = useCallback((roster) => {
    // Clear any timers still pending from a prior flip before scheduling new ones,
    // so repeated invocations never leak setTimeout handles (mount cleanup only
    // fires on unmount).
    flipTimers.current.forEach(clearTimeout);
    flipTimers.current = [];
    // Orchestrator + weather first, then category agents fan out.
    setAgents(roster.map((a) => ({ ...a, status: "standby" })));
    const order = ["ORCHESTRATOR", "WEATHER", ...CATEGORY_ORDER];
    order.forEach((name, i) => {
      const t = setTimeout(() => {
        setAgents((prev) =>
          prev.map((a) => (a.name === name ? { ...a, status: "running" } : a))
        );
      }, 350 * (i + 1));
      flipTimers.current.push(t);
    });
  }, []);

  // Post-login bootstrap: session, weather, agents, bag; flip agents. Opens
  // the drawer the visitor was originally after (pending intent), or the
  // stylist chat by default (§5.12); a pending add-to-bag replays too.
  const onAuthed = useCallback(
    async ({ token: tok, email }) => {
      setToken(tok);
      setUserEmail(email || parseJwt(tok).email || "");
      setAuthed(true);
      setAuthPopup(null);

      const intent = pendingIntentRef.current;
      pendingIntentRef.current = null;
      if (intent?.type === "drawer") {
        if (intent.drawer === "terminal") setTerminalAgent(null);
        setDrawer(intent.drawer);
      } else if (intent?.type === "add" && intent.item) {
        // Replay the add the visitor attempted while signed out.
        setBag((prev) =>
          prev.some((i) => i.item_id === intent.item.item_id)
            ? prev
            : [...prev, intent.item]
        );
        addToBag(tok, intent.item).then((resp) => {
          if (resp?.items?.length) {
            setBag((prev) => hydrate(resp.items, [...prev, ...catalog]));
          }
        });
        setDrawer("bag");
      } else {
        setDrawer("chat"); // stylist chat auto-opens (§5.12)
      }

      const [sess, wx, roster, railItems, bagItems] = await Promise.all([
        getSession(tok),
        getWeather(tok),
        getAgents(tok),
        getForecastRail(tok),
        getBag(tok),
      ]);
      if (sess) setSession(sess);
      if (wx) setWeather(Array.isArray(wx) ? wx : wx.days || wx.forecast || null);
      // Refresh the rail from catalog/deals the agents surfaced for this session.
      const activeCatalog =
        Array.isArray(railItems) && railItems.length ? railItems : catalog;
      if (Array.isArray(railItems) && railItems.length) setCatalog(railItems);
      // Self-heal: purge legacy AI rows persisted without a real price (from
      // pre-fix sessions), so the auto-kit can rebuild them correctly.
      let goodRows = Array.isArray(bagItems) ? bagItems : [];
      const staleRows = goodRows.filter(
        (r) => r.ai_pick && !(Number(r.price) > 0)
      );
      if (staleRows.length) {
        staleRows.forEach((r) => removeFromBag(tok, r.item_id));
        goodRows = goodRows.filter((r) => !staleRows.includes(r));
      }
      if (goodRows.length) {
        // Hydrate bag rows against the catalog for titles/prices/images.
        setBag(hydrate(goodRows, activeCatalog));
      }
      startAgentFlip(roster && roster.length ? roster : STANDBY_ROSTER);

      // First visit only: let the mesh pre-fill the bag with an AI-matched
      // kit for this forecast (each row tagged AI CHOICE, fully removable).
      maybeAutoKit(tok, sess, wx, goodRows);
    },
    [catalog, startAgentFlip]
  );

  // Ask the orchestrator for forecast-matched picks and add them to the bag,
  // tagged ai_pick so the drawer shows the AI CHOICE note. Skipped when the
  // user's bag already contains AI picks (returning visitor keeps control).
  async function maybeAutoKit(tok, sess, wx, bagItems) {
    if (aiKitRef.current) return;
    if ((bagItems || []).some((r) => r.ai_pick)) {
      aiKitRef.current = true;
      return;
    }
    aiKitRef.current = true;
    const res = await postChat(tok, COPY.chat.autoKitPrompt, {
      session: sess,
      weather: wx,
    });
    const added = aiAddPicks(res.picks || [], "AI CHOICE", tok);
    if (!added) return;
    setChatMessages((m) => [
      ...m,
      {
        role: "agent",
        agent: "ORCHESTRATOR",
        wid: "adidlabs/orchestrator-9f21",
        text:
          `I pre-filled your bag with ${added} AI-matched pieces for this ` +
          `forecast — each is tagged AI CHOICE in the bag. Remove any, or add ` +
          `your own picks from the rail.`,
      },
    ]);
  }

  // Persist ONLY rows not already in the bag (re-POSTing an existing row
  // would retag an AI CHOICE as AI ADVICE and bump its qty), merge state,
  // and return the fresh rows.
  function addFreshRows(rows, tok = token) {
    const have = new Set(bagRef.current.map((r) => r.item_id));
    const fresh = (rows || []).filter((r) => !have.has(r.item_id));
    if (!fresh.length) return [];
    setBag((prev) => [
      ...prev,
      ...fresh.filter((r) => !prev.some((p) => p.item_id === r.item_id)),
    ]);
    if (tok) {
      // Persist, then converge on the server's authoritative bag (canonical
      // prices, qty accumulation, ai notes) enriched with local images.
      Promise.all(fresh.map((row) => addToBag(tok, row))).then((resps) => {
        const last = resps.filter(Boolean).pop();
        if (last?.items?.length) {
          setBag((prev) => hydrate(last.items, [...prev, ...catalog]));
        }
      });
    }
    return fresh;
  }

  // Login auto-kit path ("AI CHOICE").
  function aiAddPicks(picks, label, tok = token) {
    const rows = (picks || []).slice(0, 6).map((p, i) => pickToRow(p, i, label));
    return addFreshRows(rows, tok).length;
  }

  // Chat-driven add ("AI ADVICE"): when the shopper NAMES a product, add that
  // exact catalog item (title tokens all present in the message); only a
  // generic ask ("add something warm") falls back to at most two of this
  // turn's picks. Returns {count, titles, already} for the confirmation line.
  async function handleChatAdd(message, picks) {
    const msgTokens = new Set(
      (message || "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)
    );
    const catalogFull = await ensureFullCatalog();
    const named = catalogFull.filter((i) => {
      const words = String(i.title || "")
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter(Boolean);
      return words.length > 1 && words.every((w) => msgTokens.has(w));
    });
    const rows = named.length
      ? named.slice(0, 3).map((m) => ({
          ...m,
          image: imageForItem(m),
          ai_pick: true,
          ai_note: "AI ADVICE",
        }))
      : (picks || []).slice(0, 2).map((p, i) => pickToRow(p, i, "AI ADVICE"));
    const fresh = addFreshRows(rows);
    return {
      count: fresh.length,
      titles: fresh.map((r) => r.title),
      already: fresh.length === 0 && rows.length > 0,
    };
  }

  function hydrate(rows, cat) {
    return rows.map((row) => {
      const match = cat.find((c) => c.item_id === (row.item_id || row.id));
      if (!match) return row;
      // Server rows may carry empty strings (or legacy zero prices) for fields
      // the client never sent — don't let them clobber known-good values.
      const filled = Object.fromEntries(
        Object.entries(row).filter(([k, v]) => {
          if (v === "" || v == null) return false;
          if ((k === "price" || k === "deal_price") && !(Number(v) > 0)) return false;
          return true;
        })
      );
      return { ...match, ...filled };
    });
  }

  // Wishlist heart toggle (client-side; hearts drive the wishlist drawer).
  function toggleHeart(item) {
    setWishlist((prev) =>
      prev.some((i) => i.item_id === item.item_id)
        ? prev.filter((i) => i.item_id !== item.item_id)
        : [...prev, item]
    );
  }

  // Open the auth popup remembering what the visitor was trying to do; the
  // intent replays right after login. New visitors land on JOIN THE LAB.
  function requireAuth(intent) {
    pendingIntentRef.current = intent || null;
    setAuthPopup(pendingEmail ? "login" : "register");
  }

  // Add to bag — account-gated (the bag is per-user server state). Signed-in:
  // optimistic local update, then converge on the server's authoritative bag.
  function handleAddToBag(item) {
    if (!authed) {
      requireAuth({ type: "add", item });
      return;
    }
    setBag((prev) =>
      prev.some((i) => i.item_id === item.item_id) ? prev : [...prev, item]
    );
    if (token) {
      addToBag(token, item).then((resp) => {
        if (resp?.items?.length) {
          setBag((prev) => hydrate(resp.items, [...prev, ...catalog]));
        }
      });
    }
    setDrawer("bag");
  }

  function handleRemoveFromBag(itemId) {
    setBag((prev) => prev.filter((i) => i.item_id !== itemId));
    if (token) removeFromBag(token, itemId);
  }

  function handleMoveToBag(item) {
    handleAddToBag(item);
    setWishlist((prev) => prev.filter((i) => i.item_id !== item.item_id));
  }

  function handleRemoveFromWishlist(itemId) {
    setWishlist((prev) => prev.filter((i) => i.item_id !== itemId));
  }

  // Account icon: account drawer when signed in, auth popup otherwise.
  function openAccount() {
    if (!authed) {
      requireAuth({ type: "drawer", drawer: "account" });
      return;
    }
    setDrawer("account");
  }

  // Sign out: back to anonymous browsing — the storefront stays fully
  // visible; only per-user state (bag, chat, terminal) drops.
  function signOut() {
    setAuthed(false);
    setToken(null);
    setUserEmail("");
    setBag([]);
    setDrawer(null);
    aiKitRef.current = false;
    setAgents((prev) => prev.map((a) => ({ ...a, status: "standby" })));
  }

  // Chat icon: reopen the stylist drawer (auth popup first when signed out —
  // POST /api/chat is a JWT route).
  function openChat() {
    if (!authed) {
      requireAuth({ type: "drawer", drawer: "chat" });
      return;
    }
    setDrawer("chat");
  }

  // Bag icon: per-user server state — auth popup first when signed out.
  function openBag() {
    if (!authed) {
      requireAuth({ type: "drawer", drawer: "bag" });
      return;
    }
    setDrawer("bag");
  }

  // Agent-card terminal: runtime session logs are a JWT route as well.
  function openTerminal(agent) {
    if (!authed) {
      requireAuth({ type: "drawer", drawer: "terminal" });
      return;
    }
    setTerminalAgent(agent || null);
    setDrawer("terminal");
  }

  function scrollToRail() {
    railRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Live 3-day temperature band for the product-card context line — no
  // invented numbers: render nothing until the real forecast arrives.
  const forecastBand = (() => {
    const days = Array.isArray(weather) ? weather.slice(0, 3) : [];
    const los = days
      .map((d) => Number(d.lo ?? d.tempMin ?? d.temp_min))
      .filter(Number.isFinite);
    const his = days
      .map((d) => Number(d.hi ?? d.tempMax ?? d.temp_max))
      .filter(Number.isFinite);
    if (!los.length || !his.length) return null;
    return `FORECAST READY · ${Math.round(Math.min(...los))}–${Math.round(Math.max(...his))}°C`;
  })();

  return (
    <>
      <TopUtilityBar />
      <Header
        authed={authed}
        wishlistCount={wishlist.length}
        bagCount={bag.length}
        onArchitecture={() => setDrawer("arch")}
        onChat={openChat}
        onAccount={openAccount}
        onWishlist={() => setDrawer("wishlist")}
        onBag={openBag}
      />
      <HeroBanner onShopNow={scrollToRail} />
      <StatsStrip />
      <WeatherBar session={session} weather={weather} />
      <FeatureCards
        onAction={(action) => {
          if (action === "rail") scrollToRail();
          else if (action === "chat") openChat();
          else if (action === "agents" || action === "telemetry") {
            document
              .querySelector(action === "agents" ? ".agents-panel" : ".litellm-panel")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }}
      />

      <main>
        <ProductRail
          ref={railRef}
          items={catalog}
          wishlist={wishlist}
          contextLine={forecastBand}
          onToggleHeart={toggleHeart}
          onAddToBag={handleAddToBag}
          onBrowse={(cat) => {
            setBrowseCategory(cat);
            setDrawer("browse");
          }}
        />
        <AgentsPanel agents={agents} onTerminal={openTerminal} />
        <LiteLLMPanel />
        <AgentBanner onLearnMore={openChat} onReview={() => setDrawer("bag")} />
      </main>

      <Footer />

      {/* Auth popup — opened only by account-gated actions; dismissible. */}
      {!authed && authPopup === "register" && (
        <RegistrationGate
          onRegistered={(email) => {
            setPendingEmail(email);
            setAuthPopup("login");
          }}
          onSwitchToLogin={() => setAuthPopup("login")}
          onClose={() => {
            pendingIntentRef.current = null;
            setAuthPopup(null);
          }}
        />
      )}

      {!authed && authPopup === "login" && (
        <LoginModal
          prefillEmail={pendingEmail}
          onAuthed={onAuthed}
          onSwitchToRegister={() => setAuthPopup("register")}
          onClose={() => {
            pendingIntentRef.current = null;
            setAuthPopup(null);
          }}
        />
      )}

      {/* Drawers (mutually exclusive). */}
      {drawer === "chat" && authed && (
        <StylistChat
          token={token}
          session={session}
          weather={weather}
          agents={agents}
          messages={chatMessages}
          onMessages={setChatMessages}
          onAiAdd={handleChatAdd}
          onClose={() => setDrawer(null)}
        />
      )}
      {drawer === "arch" && <ArchitectureDrawer onClose={() => setDrawer(null)} />}
      {drawer === "wishlist" && (
        <WishlistDrawer
          items={wishlist}
          onMoveToBag={handleMoveToBag}
          onRemove={handleRemoveFromWishlist}
          onClose={() => setDrawer(null)}
        />
      )}
      {drawer === "bag" && (
        <BagDrawer
          items={bag}
          onRemove={handleRemoveFromBag}
          onClose={() => setDrawer(null)}
        />
      )}
      {drawer === "terminal" && authed && (
        <TerminalDrawer
          token={token}
          agent={terminalAgent}
          onClose={() => setDrawer(null)}
        />
      )}
      {drawer === "browse" && browseCategory && (
        <CategoryDrawer
          category={browseCategory}
          onAddToBag={handleAddToBag}
          onClose={() => setDrawer(null)}
        />
      )}
      {drawer === "account" && authed && (
        <AccountDrawer
          email={userEmail}
          claims={parseJwt(token || "")}
          onSignOut={signOut}
          onClose={() => setDrawer(null)}
        />
      )}
    </>
  );
}

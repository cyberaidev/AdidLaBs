import { useCallback, useEffect, useRef, useState } from "react";
import { COPY } from "./copy.js";
import {
  getSession,
  getWeather,
  getAgents,
  getForecastRail,
  getBag,
  addToBag,
  removeFromBag,
  postChat,
} from "./api.js";
import { productTile } from "./data/fallbackCatalog.js";

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
  return {
    item_id: pick.item_id || `ai-${category.toLowerCase()}-${index + 1}`,
    title,
    category,
    price,
    deal_price: dealPrice,
    image: productTile(category, title),
    ai_pick: true,
    ai_note: label,
  };
}

// Roster with standby status, used until GET /api/agents responds (or as fallback).
const STANDBY_ROSTER = COPY.agents.map((a) => ({ ...a, status: "standby" }));

// Category agents flip to running after orchestrator + weather (§5.9).
const CATEGORY_ORDER = ["SHOES", "PANTS", "TSHIRT", "JUMPER", "JACKET", "ACCESSORY"];

export default function App() {
  // Gating state (§7). Mandatory order: RegistrationGate → LoginModal → authed.
  const [registered, setRegistered] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [pendingEmail, setPendingEmail] = useState("");
  const [token, setToken] = useState(null);

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

  const railRef = useRef(null);
  const flipTimers = useRef([]);

  // Product-rail items load immediately (static forecast set ensures the rail
  // renders pre-deploy). Post-deploy these come from catalog/deals surfaced by the
  // agents via GET /api/agents (design.md §7.1 / :210) — there is no /api/catalog route.
  useEffect(() => {
    let alive = true;
    getForecastRail(null).then((items) => {
      if (alive) setCatalog(items);
    });
    return () => {
      alive = false;
      flipTimers.current.forEach(clearTimeout);
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

  // Post-login bootstrap: session, weather, agents, bag; open chat; flip agents.
  const onAuthed = useCallback(
    async ({ token: tok, email }) => {
      setToken(tok);
      setUserEmail(email || parseJwt(tok).email || "");
      setAuthed(true);
      setShowLogin(false);
      setDrawer("chat"); // stylist chat auto-opens (§5.12)

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
      if (Array.isArray(bagItems) && bagItems.length) {
        // Hydrate bag rows against the catalog for titles/prices/images.
        setBag(hydrate(bagItems, activeCatalog));
      }
      startAgentFlip(roster && roster.length ? roster : STANDBY_ROSTER);

      // First visit only: let the mesh pre-fill the bag with an AI-matched
      // kit for this forecast (each row tagged AI CHOICE, fully removable).
      maybeAutoKit(tok, sess, wx, bagItems);
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

  // Shared AI-add path: maps orchestrator picks to bag rows (correct catalog
  // pricing), persists them, merges local state, and returns how many were
  // added. Used by the login auto-kit ("AI CHOICE") and by chat-requested
  // adds ("AI ADVICE").
  function aiAddPicks(picks, label, tok = token) {
    const rows = (picks || [])
      .slice(0, 6)
      .map((p, i) => pickToRow(p, i, label));
    if (!rows.length) return 0;
    rows.forEach((row) => tok && addToBag(tok, row));
    let addedCount = 0;
    setBag((prev) => {
      const have = new Set(prev.map((r) => r.item_id));
      const fresh = rows.filter((r) => !have.has(r.item_id));
      addedCount = fresh.length;
      return [...prev, ...fresh];
    });
    return rows.length;
  }

  function hydrate(rows, cat) {
    return rows.map((row) => {
      const match = cat.find((c) => c.item_id === (row.item_id || row.id));
      if (!match) return row;
      // Server rows may carry empty strings for fields the client never sent —
      // don't let them clobber the catalog's title/category/image.
      const filled = Object.fromEntries(
        Object.entries(row).filter(([, v]) => v !== "" && v != null)
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

  // Add to bag — optimistic local update + POST /api/bag when authed.
  function handleAddToBag(item) {
    setBag((prev) =>
      prev.some((i) => i.item_id === item.item_id) ? prev : [...prev, item]
    );
    if (token) addToBag(token, item);
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

  // Account icon: account drawer when signed in, login otherwise.
  function openAccount() {
    if (!registered) return; // gate is already blocking
    if (!authed) {
      setShowLogin(true);
      return;
    }
    setDrawer("account");
  }

  // Sign out: clear all session state back to the registered-but-logged-out view.
  function signOut() {
    setAuthed(false);
    setToken(null);
    setUserEmail("");
    setSession(null);
    setWeather(null);
    setBag([]);
    setDrawer(null);
    aiKitRef.current = false;
    setAgents(STANDBY_ROSTER);
    setShowLogin(true);
  }

  // Chat icon: reopen the stylist drawer (login first when signed out).
  function openChat() {
    if (!authed) {
      if (registered) setShowLogin(true);
      return;
    }
    setDrawer("chat");
  }

  // Agent-card terminal: read that agent's runtime session lines (login first).
  function openTerminal(agent) {
    if (!authed) {
      if (registered) setShowLogin(true);
      return;
    }
    setTerminalAgent(agent || null);
    setDrawer("terminal");
  }

  function scrollToRail() {
    railRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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
        onBag={() => setDrawer("bag")}
      />
      <HeroBanner onShopNow={scrollToRail} />
      <WeatherBar authed={authed} session={session} weather={weather} />

      <main>
        <ProductRail
          ref={railRef}
          items={catalog}
          wishlist={wishlist}
          onToggleHeart={toggleHeart}
          onAddToBag={handleAddToBag}
          onBrowse={(cat) => {
            setBrowseCategory(cat);
            setDrawer("browse");
          }}
        />
        <AgentsPanel agents={agents} onTerminal={openTerminal} />
        <LiteLLMPanel />
      </main>

      <Footer />

      {/* Gating: registration must complete before login (§7). */}
      {!registered && (
        <RegistrationGate
          onRegistered={(email) => {
            setPendingEmail(email);
            setRegistered(true);
            setShowLogin(true);
          }}
          onSwitchToLogin={() => {
            setRegistered(true);
            setShowLogin(true);
          }}
        />
      )}

      {registered && !authed && showLogin && (
        <LoginModal
          prefillEmail={pendingEmail}
          onAuthed={onAuthed}
          onSwitchToRegister={() => {
            setShowLogin(false);
            setRegistered(false);
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
          onAiAdd={(picks, label) => aiAddPicks(picks, label)}
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

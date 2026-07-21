// Thin API client for the AdidLaBs HTTP API. Every call targets VITE_API_URL and
// attaches the Cognito Bearer JWT when available. All functions degrade gracefully
// (return null / [] / a fallback) so the SPA renders before any backend is deployed.
//
// Routes (design.md §7.1):
//   GET    /api/session   time + IP geolocation
//   GET    /api/weather   3-day forecast (Open-Meteo)
//   GET    /api/bag       read bag
//   POST   /api/bag       add item
//   DELETE /api/bag       remove item
//   POST   /api/chat      stylist chat turn
//   GET    /api/agents    agent roster + identities + status

import { COPY } from "./copy.js";
import { FALLBACK_CATALOG } from "./data/fallbackCatalog.js";

const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

function headers(token) {
  const h = { "Content-Type": "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

// Returns null on any failure (missing BASE, network error, non-2xx) so callers
// can fall back to static content without throwing. `query` appends URL-encoded
// query params (used for DELETE, which avoids a request body — DELETE bodies are
// dropped by some proxies/CDNs — while still hitting the contract's DELETE /api/bag).
async function request(method, path, { token, body, query } = {}) {
  if (!BASE) return null;
  try {
    const qs = query
      ? "?" + new URLSearchParams(query).toString()
      : "";
    const res = await fetch(`${BASE}${path}${qs}`, {
      method,
      headers: headers(token),
      body: body != null ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) return null;
    if (res.status === 204) return true;
    const text = await res.text();
    return text ? JSON.parse(text) : true;
  } catch {
    return null;
  }
}

export function getSession(token) {
  return request("GET", "/api/session", { token });
}

export function getWeather(token) {
  return request("GET", "/api/weather", { token });
}

// Fetches the raw /api/agents payload once. The contract's GET /api/agents returns
// the agent roster + identities + status, and may also surface catalog/deals
// recommendations (design.md §7.1 lists exactly five route groups — there is no
// dedicated /api/catalog endpoint; the product rail is seeded from what the agents
// surface, or from a static forecast set). Returns the parsed object or null.
async function getAgentsPayload(token) {
  return request("GET", "/api/agents", { token });
}

// Normalizes any agents payload shape into a roster array.
function extractRoster(payload) {
  if (Array.isArray(payload) && payload.length) return payload;
  if (payload && Array.isArray(payload.agents) && payload.agents.length) {
    return payload.agents;
  }
  return null;
}

// Pulls rail items out of the agents payload if the agents surfaced any
// recommendations/deals; the field name varies by backend, so we probe a few.
function extractRecommendations(payload) {
  if (!payload || Array.isArray(payload)) return null;
  const rec =
    payload.recommendations || payload.catalog || payload.deals || payload.rail;
  return Array.isArray(rec) && rec.length ? rec : null;
}

export async function getAgents(token) {
  const roster = extractRoster(await getAgentsPayload(token));
  if (roster) return roster;
  // Static fallback roster with standby status.
  return COPY.agents.map((a) => ({ ...a, status: "standby" }));
}

// Product-rail source (design.md §7.1 / :210). Items come from the catalog/deals
// surfaced by the agents via GET /api/agents; when the backend is unreachable or
// surfaces no recommendations we render the static forecast set. There is no
// out-of-contract /api/catalog call.
export async function getForecastRail(token) {
  const rec = extractRecommendations(await getAgentsPayload(token));
  return rec || FALLBACK_CATALOG;
}

export async function getBag(token) {
  const data = await request("GET", "/api/bag", { token });
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

export function addToBag(token, item) {
  // Persist the descriptive fields too, so bag rows survive reloads with their
  // title/category/price instead of empty strings (bag.py preserves supplied
  // fields and only seeds absent ones).
  return request("POST", "/api/bag", {
    token,
    body: {
      item_id: item.item_id,
      title: item.title,
      category: item.category,
      price: item.deal_price ?? item.price,
      image: item.image,
      qty: 1,
      ...(item.ai_pick ? { ai_pick: true, ai_note: item.ai_note || "AI CHOICE" } : {}),
    },
  });
}

// Full category list for manual browsing (public). Returns { count, items }.
export function getCatalog(category, limit = 60) {
  return request("GET", "/api/catalog", {
    query: category ? { category, limit } : { limit },
  });
}

// Removes a bag item via DELETE /api/bag. The item_id travels as a query param
// rather than a request body: fetch permits DELETE bodies, but they are fragile
// across proxies/CDNs and silently ignored by some servers, so a query param is
// the more robust way to hit the same contract route.
export function removeFromBag(token, itemId) {
  return request("DELETE", "/api/bag", { token, query: { item_id: itemId } });
}

// Web-terminal feed: recent AgentCore runtime session lines, optionally
// filtered to one agent's wid. Returns { log_group, events } or null.
export function getTerminal(token, wid) {
  return request("GET", "/api/terminal", {
    token,
    query: wid ? { wid, limit: 150 } : { limit: 150 },
  });
}

// LiteLLM gateway telemetry: Bedrock token usage per model route (public).
// Returns { window_hours, models, totals } or null.
export function getTelemetry() {
  return request("GET", "/api/telemetry", {});
}

// Posts a chat turn; returns { reply, agent, wid } shape or a deterministic demo
// reply when the backend is unreachable so the drawer always responds.
export async function postChat(token, message, context) {
  const data = await request("POST", "/api/chat", {
    token,
    body: { message, context },
  });
  if (data && (data.reply || data.message)) {
    return {
      reply: data.reply || data.message,
      agent: data.agent || "ORCHESTRATOR",
      wid: data.wid || "adidlabs/orchestrator-9f21",
      picks: Array.isArray(data.picks) ? data.picks : [],
    };
  }
  return {
    reply:
      "Reading your 3-day forecast and matching pieces across the collection… " +
      "(demo mode — connect VITE_API_URL for live stylist picks).",
    agent: "ORCHESTRATOR",
    wid: "adidlabs/orchestrator-9f21",
  };
}

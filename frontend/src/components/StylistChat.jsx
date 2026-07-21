import { useEffect, useRef, useState } from "react";
import { COPY } from "../copy.js";
import { Drawer } from "./Drawer.jsx";
import { Wordmark } from "./Wordmark.jsx";
import { postChat } from "../api.js";

// WMO daily weathercode -> short label (subset; mirrors backend/chat.py).
const WMO = {
  0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
  45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
  61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow",
  73: "snow", 75: "heavy snow", 80: "showers", 81: "showers",
  82: "heavy showers", 95: "thunderstorms", 96: "thunderstorms",
  99: "thunderstorms",
};

// "Milan, IT — next 3 days: TUE 31°/23° showers · …" (same shape the backend
// prefixes onto live replies).
function contextLine(session, weather) {
  const days = Array.isArray(weather) ? weather : weather?.days || [];
  const city = session?.city;
  const region = session?.region || session?.country;
  const place = city ? (region ? `${city}, ${region}` : city) : "";
  const parts = days
    .slice(0, 3)
    .map((d) => {
      let seg = String(d.day || d.date || "").trim();
      if (d.hi != null && d.lo != null) {
        seg = `${seg} ${Math.round(d.hi)}°/${Math.round(d.lo)}°`.trim();
      }
      const label = WMO[d.weathercode] || d.label || "";
      if (label) seg = `${seg} ${label}`.trim();
      return seg;
    })
    .filter(Boolean);
  if (!place && !parts.length) return "";
  if (!parts.length) return place;
  const line = parts.join(" · ");
  return place ? `${place} — next 3 days: ${line}` : `Next 3 days: ${line}`;
}

// Stylist chat drawer (§5.13). Auto-opens after login. Orchestrator-seeded greeting,
// a weather-agent context report as soon as the session loads, user/agent bubbles,
// composer POSTs /api/chat, and an 8-square "thinking" row. History lives in App
// state (messages/onMessages) so closing the drawer never loses the conversation.
// "add a rain jacket to my bag", "put shoes in the bag", "bag it" …
const ADD_INTENT = /\b(add|put|drop|throw|stick|bag it|to (?:my|the) bag|buy)\b/i;

export function StylistChat({
  token,
  session,
  weather,
  agents,
  messages,
  onMessages,
  onAiAdd,
  onClose,
}) {
  const setMessages = onMessages;
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bodyRef = useRef(null);

  // As soon as the IP-derived session + forecast land, the weather agent
  // reports the city and 3-day outlook right in the chat (§ the chat must
  // report location + weather, not just the weather bar). Announce exactly
  // once per session — the guard reads the persisted history, so reopening
  // the drawer never repeats it.
  useEffect(() => {
    if (messages.some((m) => m.text?.startsWith("Here is your local read"))) return;
    const line = contextLine(session, weather);
    if (!line) return;
    setMessages((m) =>
      m.some((x) => x.text?.startsWith("Here is your local read"))
        ? m
        : [
            ...m,
            {
              role: "agent",
              agent: "WEATHER",
              wid: "adidlabs/weather-3b7c",
              text: `Here is your local read — ${line}. Ask for a look and I will match it to this window.`,
            },
          ]
    );
  }, [session, weather, messages, setMessages]);

  useEffect(() => {
    // Keep the message list scrolled to the newest turn.
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, thinking]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setThinking(true);
    const context = { session, weather };
    const res = await postChat(token, text, context);
    setMessages((m) => [
      ...m,
      { role: "agent", agent: res.agent, wid: res.wid, text: res.reply },
    ]);
    // Chat-driven shopping: a named product ("add Aurora Black Belt") adds
    // exactly that catalog item; only generic asks fall back to this turn's
    // picks (max 2). The confirmation names what ACTUALLY landed in the bag.
    if (onAiAdd && ADD_INTENT.test(text)) {
      const outcome = await onAiAdd(text, res.picks || []);
      if (outcome?.count) {
        setMessages((m) => [
          ...m,
          {
            role: "agent",
            agent: "ORCHESTRATOR",
            wid: "adidlabs/orchestrator-9f21",
            text: `Added to your bag (tagged AI ADVICE): ${outcome.titles.join(", ")}. Open the bag to keep or remove.`,
          },
        ]);
      } else if (outcome?.already) {
        setMessages((m) => [
          ...m,
          {
            role: "agent",
            agent: "ORCHESTRATOR",
            wid: "adidlabs/orchestrator-9f21",
            text: "Those picks are already in your bag — nothing new added.",
          },
        ]);
      }
    }
    setThinking(false);
  }

  return (
    <Drawer titleId="chat-title" className="chat" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="chat-title">
          <Wordmark />
          {COPY.chat.title}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close stylist chat"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body" ref={bodyRef}>
        <div className="chat-msgs">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg user">
                {m.text}
              </div>
            ) : (
              <div key={i}>
                <div className="msg-label">
                  {m.agent} · {m.wid}
                </div>
                <div className="msg agent">{m.text}</div>
              </div>
            )
          )}
        </div>
        {thinking && (
          <div className="chat-thinking" aria-label="Agents thinking">
            {agents.map((a) => (
              <span
                key={a.wid}
                className={`status-dot ${a.status === "running" ? "running" : ""}`}
                style={{
                  background:
                    a.status === "running" ? "var(--ok-green)" : "var(--standby)",
                }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="drawer-foot">
        <form className="composer" onSubmit={send}>
          <input
            type="text"
            aria-label="Message the stylist"
            placeholder={COPY.chat.placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit">{COPY.chat.send}</button>
        </form>
      </div>
    </Drawer>
  );
}

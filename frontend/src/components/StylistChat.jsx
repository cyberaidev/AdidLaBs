import { useEffect, useRef, useState } from "react";
import { COPY } from "../copy.js";
import { Drawer } from "./Drawer.jsx";
import { Wordmark } from "./Wordmark.jsx";
import { postChat } from "../api.js";

// Stylist chat drawer (§5.13). Auto-opens after login. Orchestrator-seeded greeting,
// user/agent bubbles, composer POSTs /api/chat, and an 8-square "thinking" row.
export function StylistChat({ token, session, weather, agents, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "agent",
      agent: "ORCHESTRATOR",
      wid: "adidlabs/orchestrator-9f21",
      text: COPY.chat.seed,
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bodyRef = useRef(null);

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

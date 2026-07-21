import { useEffect, useRef, useState } from "react";
import { Drawer } from "./Drawer.jsx";
import { getTerminal } from "../api.js";

const POLL_MS = 5000;

function hhmmss(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// Web terminal drawer: live CloudWatch session lines from the AgentCore
// runtime, filtered to one agent's wid (or the whole mesh when wid is null).
// Read-only by design — it observes sessions, it cannot drive them.
export function TerminalDrawer({ token, agent, onClose }) {
  const [events, setEvents] = useState(null); // null = loading
  const [logGroup, setLogGroup] = useState("");
  const bodyRef = useRef(null);
  const wid = agent?.wid || null;

  useEffect(() => {
    let alive = true;
    async function poll() {
      const data = await getTerminal(token, wid);
      if (!alive) return;
      setEvents(data?.events || []);
      setLogGroup(data?.log_group || "");
    }
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [token, wid]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [events]);

  return (
    <Drawer titleId="terminal-title" className="terminal" onClose={onClose}>
      <div className="drawer-head terminal-head">
        <span className="drawer-title" id="terminal-title">
          <span className="term-live" aria-hidden="true" />
          {agent ? `${agent.name} · ${agent.wid}` : "AGENT MESH · ALL SESSIONS"}
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close terminal"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body terminal-body" ref={bodyRef}>
        {events === null ? (
          <p className="term-line term-dim">connecting to runtime log stream…</p>
        ) : events.length === 0 ? (
          <>
            <p className="term-line term-dim">
              $ tail -f {logGroup || "/aws/bedrock-agentcore/runtimes/adidlabs_agents-*"}
            </p>
            <p className="term-line term-dim">
              no session lines in the last hour — send the stylist a message to
              wake the mesh, then watch this terminal.
            </p>
          </>
        ) : (
          <>
            <p className="term-line term-dim">$ tail -f {logGroup}</p>
            {events.map((e, i) => (
              <p className="term-line" key={i}>
                <span className="term-ts">[{hhmmss(e.ts)}]</span> {e.message}
              </p>
            ))}
          </>
        )}
      </div>

      <div className="drawer-foot terminal-foot">
        <span>
          Read-only session view · CloudWatch · refreshes every {POLL_MS / 1000}s
        </span>
      </div>
    </Drawer>
  );
}

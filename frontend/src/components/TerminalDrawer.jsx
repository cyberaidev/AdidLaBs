import { useEffect, useRef, useState } from "react";
import { Drawer } from "./Drawer.jsx";
import { getTerminal, getTrace } from "../api.js";

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
  const [trace, setTrace] = useState(null); // null = loading, {} shape after
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

  // OTEL per-session breakdown — one fetch per drawer open (Logs Insights
  // queries are not free; the refresh button re-runs it on demand).
  useEffect(() => {
    let alive = true;
    getTrace(token).then((data) => {
      if (alive) setTrace(data || {});
    });
    return () => {
      alive = false;
    };
  }, [token]);

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

      <div className="trace-panel">
        <div className="trace-head">
          <span>SESSION TRACE · OPENTELEMETRY</span>
          <button
            type="button"
            className="trace-refresh"
            onClick={() => {
              setTrace(null);
              getTrace(token).then((data) => setTrace(data || {}));
            }}
          >
            ↻ REFRESH
          </button>
        </div>
        {trace === null ? (
          <p className="trace-dim">querying aws/spans (Logs Insights)…</p>
        ) : !trace.components?.length ? (
          <p className="trace-dim">
            {trace.note ||
              "No spans for this session yet — chat with the stylist, wait " +
              "~1 min for span delivery, then refresh."}
          </p>
        ) : (
          (() => {
            const max = Math.max(...trace.components.map((c) => c.total_ms));
            return trace.components.map((c) => (
              <div className="trace-row" key={c.component}>
                <span className="trace-name">{c.component}</span>
                <span className="trace-bar-track">
                  <span
                    className="trace-bar"
                    style={{ width: `${Math.max(3, (c.total_ms / max) * 100)}%` }}
                  />
                </span>
                <span className="trace-meta">
                  {c.calls}× · {c.total_ms >= 1000
                    ? `${(c.total_ms / 1000).toFixed(2)}s`
                    : `${Math.round(c.total_ms)}ms`}{" "}
                  <i>avg {Math.round(c.avg_ms)}ms</i>
                </span>
              </div>
            ));
          })()
        )}
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

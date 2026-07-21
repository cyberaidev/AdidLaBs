import { useEffect, useRef, useState } from "react";
import { COPY } from "../copy.js";
import { getTelemetry } from "../api.js";

const POLL_MS = 15000;

function n(x) {
  return Number(x || 0).toLocaleString();
}

// LITELLM GATEWAY panel: incremental Bedrock token usage + telemetry per model
// route, polled from GET /api/telemetry (CloudWatch AWS/Bedrock metrics).
// Sits directly under AGENTS ON BEDROCK AGENTCORE.
export function LiteLLMPanel() {
  const [data, setData] = useState(null);
  const baselineRef = useRef(null); // totals at page load → session delta

  useEffect(() => {
    let alive = true;
    async function poll() {
      const t = await getTelemetry();
      if (!alive || !t) return;
      if (!baselineRef.current && t.totals) baselineRef.current = t.totals;
      setData(t);
    }
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const totals = data?.totals || { tokens_in: 0, tokens_out: 0, invocations: 0, tokens: 0 };
  const base = baselineRef.current || totals;
  const delta = Math.max(0, (totals.tokens || 0) - (base.tokens || 0));
  const models = data?.models || [];

  return (
    <section className="section container litellm-panel">
      <h2 className="section-heading">{COPY.litellm.heading}</h2>
      <p className="section-sub">
        {COPY.litellm.sub} · last {data?.window_hours ?? 24}h ·{" "}
        {data?.region || "ap-southeast-2"}
      </p>

      <div className="tele-stats">
        <div className="tele-stat">
          <span className="tele-label">TOKENS IN</span>
          <span className="tele-value">{n(totals.tokens_in)}</span>
        </div>
        <div className="tele-stat">
          <span className="tele-label">TOKENS OUT</span>
          <span className="tele-value">{n(totals.tokens_out)}</span>
        </div>
        <div className="tele-stat">
          <span className="tele-label">INVOCATIONS</span>
          <span className="tele-value">{n(totals.invocations)}</span>
        </div>
        <div className="tele-stat">
          <span className="tele-label">THIS VISIT</span>
          <span className="tele-value">+{n(delta)}</span>
        </div>
      </div>

      {models.length > 0 ? (
        <div className="tele-rows">
          {models.map((m) => (
            <div className="tele-row" key={m.model_id}>
              <span className="chip">{m.route}</span>
              <span className="tele-model">{m.model_id}</span>
              <span className="tele-nums">
                in {n(m.tokens_in)} · out {n(m.tokens_out)} · {n(m.invocations)}{" "}
                calls · {n(m.avg_latency_ms)} ms
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="tele-empty">{COPY.litellm.empty}</p>
      )}
      <p className="tele-foot">{COPY.litellm.foot}</p>
    </section>
  );
}

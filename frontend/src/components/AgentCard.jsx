import { COPY } from "../copy.js";

// Single agent card (§5.10). Renders the wid identity and route chip verbatim.
export function AgentCard({ agent }) {
  const running = agent.status === "running";
  return (
    <div className="agent-card">
      <div className="agent-name">{agent.name}</div>
      <div className="agent-wid">{agent.wid}</div>
      <div className="agent-meta">
        <span className="chip">{agent.route}</span>
        <span className={`status ${running ? "running" : ""}`}>
          <span className="status-dot" aria-hidden="true" />
          {running ? COPY.agentsPanel.statusRunning : COPY.agentsPanel.statusStandby}
        </span>
      </div>
    </div>
  );
}

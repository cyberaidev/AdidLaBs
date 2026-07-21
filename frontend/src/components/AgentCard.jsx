import { COPY } from "../copy.js";
import { TerminalIcon } from "./icons.jsx";

// Single agent card (§5.10). Renders the wid identity and route chip verbatim,
// plus a web-terminal button that opens this agent's live session view.
export function AgentCard({ agent, onTerminal }) {
  const running = agent.status === "running";
  return (
    <div className="agent-card">
      <div className="agent-card-top">
        <div>
          <div className="agent-name">{agent.name}</div>
          <div className="agent-wid">{agent.wid}</div>
        </div>
        {onTerminal && (
          <button
            type="button"
            className="icon-btn term-btn"
            aria-label={`Open ${agent.name} session terminal`}
            title="Session terminal"
            onClick={() => onTerminal(agent)}
          >
            <TerminalIcon />
          </button>
        )}
      </div>
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

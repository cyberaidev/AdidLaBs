import { COPY } from "../copy.js";
import { AgentCard } from "./AgentCard.jsx";

// AGENTS ON BEDROCK AGENTCORE panel (§5.9). Grid of 8 cards in fixed roster order.
// Status flips standby → running after login (managed by App state).
export function AgentsPanel({ agents }) {
  return (
    <section className="section container">
      <h2 className="section-heading">{COPY.agentsPanel.heading}</h2>
      <p className="section-sub">{COPY.agentsPanel.sub}</p>
      <div className="agents-grid">
        {agents.map((agent) => (
          <AgentCard key={agent.wid} agent={agent} />
        ))}
      </div>
    </section>
  );
}

import { useState } from "react";
import { Drawer } from "./Drawer.jsx";
import { Wordmark } from "./Wordmark.jsx";

// External agent integrations offered under the account. Demo stubs: the
// CONNECT toggle simulates an A2A handshake and persists in localStorage —
// no real external calls are made.
const CONNECTORS = [
  {
    id: "openclaw",
    name: "OpenClaw",
    desc: "Personal AI agent — sync your lab picks and forecasts over A2A.",
  },
  {
    id: "hermes",
    name: "Hermes",
    desc: "Messenger AI agent — get styling drops and deal alerts relayed.",
  },
];

function connKey(id) {
  return `adidlabs_conn_${id}`;
}

// Account drawer: signed-in user details + agent-connection stubs + sign out.
export function AccountDrawer({ email, claims, onSignOut, onClose }) {
  const [conns, setConns] = useState(() =>
    Object.fromEntries(
      CONNECTORS.map((c) => [c.id, localStorage.getItem(connKey(c.id)) === "1"])
    )
  );

  function toggle(id) {
    setConns((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      localStorage.setItem(connKey(id), next[id] ? "1" : "0");
      return next;
    });
  }

  return (
    <Drawer titleId="account-title" onClose={onClose}>
      <div className="drawer-head">
        <span className="drawer-title" id="account-title">
          <Wordmark />
          ACCOUNT
        </span>
        <button
          type="button"
          className="drawer-close"
          aria-label="Close account"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="drawer-body">
        <div className="acct-block">
          <div className="acct-avatar" aria-hidden="true">
            {(email || "L")[0].toUpperCase()}
          </div>
          <div>
            <div className="acct-email">{email || "Lab member"}</div>
            <div className="acct-sub">LaB club member · AgentCore identity</div>
          </div>
        </div>

        <div className="acct-rows">
          <div className="acct-row">
            <span>User id (sub)</span>
            <code>{claims?.sub || "—"}</code>
          </div>
          <div className="acct-row">
            <span>Identity pool</span>
            <code>ap-southeast-2 · Cognito</code>
          </div>
          <div className="acct-row">
            <span>Session issued</span>
            <code>
              {claims?.iat
                ? new Date(claims.iat * 1000).toLocaleString()
                : "—"}
            </code>
          </div>
        </div>

        <h3 className="acct-heading">AGENT CONNECTIONS</h3>
        <p className="acct-note">
          Link external AI agents to your lab account (demo stubs — the A2A
          handshake is simulated, nothing leaves this browser).
        </p>
        {CONNECTORS.map((c) => (
          <div className="conn-row" key={c.id}>
            <div className="conn-info">
              <span className="conn-name">
                {c.name}
                <span
                  className={`conn-status ${conns[c.id] ? "on" : ""}`}
                >
                  {conns[c.id] ? "CONNECTED" : "NOT CONNECTED"}
                </span>
              </span>
              <span className="conn-desc">{c.desc}</span>
            </div>
            <button
              type="button"
              className="conn-btn"
              onClick={() => toggle(c.id)}
            >
              {conns[c.id] ? "DISCONNECT" : "CONNECT"}
            </button>
          </div>
        ))}
      </div>

      <div className="drawer-foot">
        <button type="button" className="checkout-btn" onClick={onSignOut}>
          SIGN OUT
        </button>
      </div>
    </Drawer>
  );
}

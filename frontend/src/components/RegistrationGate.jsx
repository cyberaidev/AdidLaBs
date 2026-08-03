import { useState } from "react";
import { COPY } from "../copy.js";
import { Modal } from "./Modal.jsx";
import { Wordmark } from "./Wordmark.jsx";
import { register } from "../auth.js";
import { isConsumerEmail } from "../data/consumerDomains.js";

// JOIN THE LAB popup (§5.11). Since the storefront is browsable anonymously,
// this appears only when the visitor clicks an account-gated action (Account,
// Bag, Stylist) and can be dismissed. Registration accepts company /
// organization email domains only — consumer mailboxes are rejected here for
// instant feedback and again server-side by the Cognito PreSignUp trigger.
// Only NAME/EMAIL/PASSWORD — never payment or sensitive IDs.
export function RegistrationGate({ onRegistered, onSwitchToLogin, onClose }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!name.trim() || !email.trim() || password.length < 6) {
      setError("Enter a name, a valid email, and a password (6+ characters).");
      return;
    }
    if (isConsumerEmail(email)) {
      setError(
        "Please use your company or organization email — consumer domains " +
        "(gmail, yahoo, outlook, icloud, …) are not accepted."
      );
      return;
    }
    setBusy(true);
    try {
      await register({ name: name.trim(), email: email.trim(), password });
      onRegistered(email.trim());
    } catch (err) {
      // Cognito wraps PreSignUp trigger rejections in a technical prefix —
      // strip it so the policy message reads cleanly.
      const msg = (err?.message || "").replace(/^PreSignUp failed with error /, "");
      setError(msg || "Registration failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal titleId="gate-title" dismissible={Boolean(onClose)} onClose={onClose}>
      <div className="modal-head">
        <Wordmark />
        <h2 className="modal-title" id="gate-title">
          {COPY.gate.title}
        </h2>
        <p className="modal-sub">{COPY.gate.sub}</p>
      </div>

      <form onSubmit={onSubmit} noValidate>
        {error && <p className="form-error">{error}</p>}
        <div className="field">
          <label htmlFor="reg-name">{COPY.gate.fields.name}</label>
          <input
            id="reg-name"
            type="text"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="reg-email">{COPY.gate.fields.email}</label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="reg-pass">{COPY.gate.fields.password}</label>
          <input
            id="reg-pass"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "…" : COPY.gate.primary}
        </button>
        <button type="button" className="btn-secondary" onClick={onSwitchToLogin}>
          {COPY.gate.secondary}
        </button>
      </form>
    </Modal>
  );
}

import { useState } from "react";
import { COPY } from "../copy.js";
import { Modal } from "./Modal.jsx";
import { Wordmark } from "./Wordmark.jsx";
import { login } from "../auth.js";

// LOG IN modal (§5.12). Shown after registration. On success App auto-opens the
// stylist chat, reveals the weather bar, and flips agents to running.
export function LoginModal({ prefillEmail, onAuthed, onSwitchToRegister }) {
  const [email, setEmail] = useState(prefillEmail || "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    try {
      const { token } = await login({ email: email.trim(), password });
      onAuthed({ token, email: email.trim() });
    } catch (err) {
      setError(err?.message || "Login failed. Check your details and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal titleId="login-title" dismissible={true} onClose={onSwitchToRegister}>
      <div className="modal-head">
        <Wordmark />
        <h2 className="modal-title" id="login-title">
          {COPY.login.title}
        </h2>
      </div>

      <form onSubmit={onSubmit} noValidate>
        {error && <p className="form-error">{error}</p>}
        <div className="field">
          <label htmlFor="login-email">{COPY.login.fields.email}</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="login-pass">{COPY.login.fields.password}</label>
          <input
            id="login-pass"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "…" : COPY.login.primary}
        </button>
        <button type="button" className="btn-secondary" onClick={onSwitchToRegister}>
          {COPY.login.secondary}
        </button>
      </form>
    </Modal>
  );
}

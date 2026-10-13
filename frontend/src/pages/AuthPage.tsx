import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, token } from "../api";

export default function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      token.set(res.access_token);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth-card">
        <h1 className="brand big">
          Reel<span>Groceries</span>
        </h1>
        <p className="muted">Saved a recipe video? Turn it into a shopping list.</p>
        <form onSubmit={submit}>
          <label>
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
        <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Log in"}
        </button>
      </div>
    </div>
  );
}

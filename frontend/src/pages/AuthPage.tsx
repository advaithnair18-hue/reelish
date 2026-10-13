import { FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, token } from "../api";

export default function AuthPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const [mode, setMode] = useState<"register" | "login">("register");
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
      navigate(next.startsWith("/") ? next : "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="welcome">
      <div className="welcome-art" aria-hidden="true">
        <div className="phone-card c1"><span>4 cloves garlic</span></div>
        <div className="phone-card c2"><span>200 g noodles</span></div>
        <div className="phone-card c3"><span>2 tbsp soy sauce</span></div>
        <img src="/icons/icon-512.png" alt="" className="welcome-logo" />
      </div>
      <h1 className="welcome-title">Saw it on your feed. Now it's on your list.</h1>
      <p className="welcome-sub">
        Share any TikTok, Reel or Short to Reel Groceries and its ingredients land on your grocery list, merged and sorted
        by aisle.
      </p>
      <form onSubmit={submit} className="form">
        <label className="field">
          <span>Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "register" ? "At least 8 characters" : ""}
          />
        </label>
        {error && <p className="notice error">{error}</p>}
        <button className="btn primary big" disabled={busy}>
          {busy ? "One moment…" : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <button className="btn text" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "New here? Create an account" : "Already have an account? Log in"}
      </button>
    </div>
  );
}

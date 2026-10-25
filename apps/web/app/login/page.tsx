"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setInfo("");
    const sb = getSupabase();
    const { error } = mode === "signin"
      ? await sb.auth.signInWithPassword({ email, password })
      : await sb.auth.signUp({ email, password });
    setBusy(false);
    if (error) { setError(error.message); return; }
    if (mode === "signup") {
      setInfo("Account created. If email confirmation is enabled, confirm the email, then sign in.");
      setMode("signin");
      return;
    }
    router.replace("/dashboard");
  }

  return (
    <main className="container" style={{ maxWidth: 420 }}>
      <div className="card" style={{ marginTop: 48 }}>
        <h1>God Mode AI Software Factory</h1>
        <p className="muted" style={{ margin: "8px 0 16px" }}>Sign in to your factory dashboard.</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "signin" ? "current-password" : "new-password"} />
          {error && <p className="error" role="alert">{error}</p>}
          {info && <p className="muted">{info}</p>}
          <button className="btn" disabled={busy} type="submit">
            {busy ? "Working..." : mode === "signin" ? "Sign in" : "Create account"}
          </button>
          <button type="button" className="btn secondary" style={{ marginLeft: 8 }}
            onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); setInfo(""); }}>
            {mode === "signin" ? "Need an account?" : "Have an account?"}
          </button>
        </form>
      </div>
    </main>
  );
}

import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { lovable } from "@/integrations/lovable/index";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Sign in | InsideLabel" },
      { name: "description", content: "Sign in to manage InsideLabel claim rules." },
      { property: "og:title", content: "Sign in | InsideLabel" },
      { property: "og:description", content: "Sign in to manage InsideLabel claim rules." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate({ to: "/admin" });
    });
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session) navigate({ to: "/admin" });
    });
    return () => data.subscription.unsubscribe();
  }, [navigate]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    if (mode === "in") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) setMsg(error.message);
    } else {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/admin` },
      });
      if (error) setMsg(error.message);
      else if (!data.session) setMsg("Check your email to confirm your account, then sign in.");
    }
    setBusy(false);
  }

  async function google() {
    const r = await lovable.auth.signInWithOAuth("google", { redirect_uri: window.location.origin + "/auth" });
    if (r.error) setMsg("Google sign-in failed. Please try again.");
  }

  return (
    <div className="min-h-screen bg-hero px-5 py-10">
      <div className="mx-auto max-w-md">
        <Link to="/" className="text-sm font-semibold text-muted-foreground">
          ← Back to scanner
        </Link>
        <div className="mt-6 rounded-3xl border border-border bg-card p-6 shadow-soft">
          <h1 className="font-display text-3xl font-extrabold">
            {mode === "in" ? "Admin sign in" : "Create admin account"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">Manage the claim rules the checker uses.</p>
          <button
            type="button"
            onClick={google}
            className="mt-6 w-full rounded-2xl border border-border bg-background py-3 font-semibold"
          >
            Continue with Google
          </button>
          <div className="my-4 text-center text-xs text-muted-foreground">or</div>
          <form onSubmit={submit} className="space-y-3">
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-2xl border border-input bg-background px-4 py-3"
            />
            <input
              type="password"
              required
              minLength={8}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-2xl border border-input bg-background px-4 py-3"
            />
            <button
              disabled={busy}
              className="btn-press w-full rounded-2xl bg-primary py-3 font-bold text-primary-foreground disabled:opacity-60"
            >
              {busy ? "Please wait…" : mode === "in" ? "Sign in" : "Create account"}
            </button>
          </form>
          {msg && <p className="mt-3 rounded-xl bg-secondary p-3 text-sm">{msg}</p>}
          <button
            type="button"
            onClick={() => setMode(mode === "in" ? "up" : "in")}
            className="mt-4 text-sm font-semibold text-primary"
          >
            {mode === "in" ? "No account yet? Create one" : "Have an account? Sign in"}
          </button>
        </div>
      </div>
    </div>
  );
}

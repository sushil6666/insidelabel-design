import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { dismissClaim, draftRules, getAdminStatus, listClaimData, saveRule } from "@/lib/admin.functions";

export const Route = createFileRoute("/_authenticated/admin")({
  head: () => ({
    meta: [
      { title: "Claim rules admin | InsideLabel" },
      { name: "description", content: "Review new front-of-pack claims and approve rules." },
      { property: "og:title", content: "Claim rules admin | InsideLabel" },
      { property: "og:description", content: "Review new front-of-pack claims and approve rules." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AdminPage,
});

const CHECK_LABELS: Record<string, string> = {
  added_sugar_present: "Flag if added sugar is listed",
  preservative_present: "Flag if a preservative is listed",
  subject_absent_or_flavour_only: "Flag if the named thing is missing or only a flavour",
  ingredient_present: "Flag if any of these words are listed",
  not_checkable: "Can't be checked from ingredients (show a note)",
};

type Rule = {
  id: string;
  label: string;
  match: string[];
  check_type: string;
  terms: string[];
  confidence: string;
  verify: boolean;
  note: string;
  status: string;
  source: string;
  example_claim: string | null;
};

function AdminPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const status = useServerFn(getAdminStatus);
  const list = useServerFn(listClaimData);
  const draft = useServerFn(draftRules);
  const dismiss = useServerFn(dismissClaim);

  const adminQ = useQuery({ queryKey: ["admin-status"], queryFn: () => status() });
  const dataQ = useQuery({
    queryKey: ["claim-data"],
    queryFn: () => list(),
    enabled: adminQ.data?.isAdmin === true,
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<"draft" | "approved" | "rejected">("draft");

  async function signOut() {
    await supabase.auth.signOut();
    qc.clear();
    navigate({ to: "/auth" });
  }

  if (adminQ.isLoading) return <Shell onSignOut={signOut}><p>Loading…</p></Shell>;
  if (!adminQ.data?.isAdmin)
    return (
      <Shell onSignOut={signOut}>
        <p className="rounded-2xl bg-secondary p-4">This account isn't the admin. Only the first account created can manage rules.</p>
      </Shell>
    );

  const unmatched = (dataQ.data?.unmatched ?? []) as Array<{ id: string; claim: string; times_seen: number }>;
  const rules = (dataQ.data?.rules ?? []) as Rule[];
  const shown = rules.filter((r) => r.status === tab);

  async function runDraft() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await draft({ data: { ids: selected.slice(0, 10) } });
      setMsg(`Drafted ${r.drafted} rule${r.drafted === 1 ? "" : "s"}${r.failed ? `, ${r.failed} couldn't be drafted` : ""}. Review them below.`);
      setSelected([]);
      setTab("draft");
      await qc.invalidateQueries({ queryKey: ["claim-data"] });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Drafting failed.");
    }
    setBusy(false);
  }

  return (
    <Shell onSignOut={signOut}>
      <section className="rounded-3xl border border-border bg-card p-5 shadow-soft">
        <h2 className="font-display text-2xl font-extrabold">New claims from scans</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Claims the checker didn't recognise. Pick up to 10 and let AI draft rules. Nothing goes live until you approve it.
        </p>
        {unmatched.length === 0 ? (
          <p className="mt-4 rounded-2xl bg-muted p-4 text-sm">No new claims yet. They'll appear here as people scan packs.</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {unmatched.map((u) => (
              <li key={u.id} className="flex items-center gap-3 rounded-2xl border border-border p-3">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-[var(--primary)]"
                  checked={selected.includes(u.id)}
                  onChange={(e) =>
                    setSelected((s) => (e.target.checked ? [...s, u.id].slice(0, 10) : s.filter((x) => x !== u.id)))
                  }
                />
                <span className="flex-1 font-medium">“{u.claim}”</span>
                <span className="text-xs text-muted-foreground">seen {u.times_seen}×</span>
                <button
                  onClick={async () => {
                    await dismiss({ data: { id: u.id } });
                    qc.invalidateQueries({ queryKey: ["claim-data"] });
                  }}
                  className="text-xs font-semibold text-muted-foreground underline"
                >
                  Ignore
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          disabled={!selected.length || busy}
          onClick={runDraft}
          className="btn-press mt-4 w-full rounded-2xl bg-primary py-3 font-bold text-primary-foreground disabled:opacity-50"
        >
          {busy ? "Drafting…" : `Draft rules with AI (${selected.length})`}
        </button>
        {msg && <p className="mt-3 rounded-xl bg-secondary p-3 text-sm">{msg}</p>}
      </section>

      <section className="mt-6">
        <div className="flex gap-2">
          {(["draft", "approved", "rejected"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-full px-4 py-2 text-sm font-semibold ${tab === t ? "bg-primary text-primary-foreground" : "bg-secondary"}`}
            >
              {t === "draft" ? "Waiting for review" : t === "approved" ? "Live" : "Rejected"} (
              {rules.filter((r) => r.status === t).length})
            </button>
          ))}
        </div>
        <div className="mt-4 space-y-4">
          {shown.length === 0 && <p className="rounded-2xl bg-muted p-4 text-sm">Nothing here.</p>}
          {shown.map((r) => (
            <RuleCard key={r.id} rule={r} />
          ))}
        </div>
      </section>
    </Shell>
  );
}

function Shell({ children, onSignOut }: { children: React.ReactNode; onSignOut: () => void }) {
  return (
    <div className="min-h-screen bg-hero px-5 py-8">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6 flex items-center justify-between">
          <Link to="/" className="text-sm font-semibold text-muted-foreground">← Scanner</Link>
          <button onClick={onSignOut} className="text-sm font-semibold text-muted-foreground underline">Sign out</button>
        </div>
        <h1 className="mb-6 font-display text-4xl font-extrabold">Claim rules</h1>
        {children}
      </div>
    </div>
  );
}

function RuleCard({ rule }: { rule: Rule }) {
  const qc = useQueryClient();
  const save = useServerFn(saveRule);
  const [r, setR] = useState(rule);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const isSeed = rule.source === "seed";

  async function commit(status: string) {
    setSaving(true);
    setErr(null);
    try {
      await save({
        data: {
          id: r.id,
          label: r.label,
          match: r.match.map((s) => s.trim()).filter(Boolean),
          check_type: r.check_type as "not_checkable",
          terms: r.terms.map((s) => s.trim()).filter(Boolean),
          confidence: r.confidence as "high",
          verify: r.verify,
          note: r.note,
          status: status as "approved",
        },
      });
      await qc.invalidateQueries({ queryKey: ["claim-data"] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed.");
    }
    setSaving(false);
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <input
          value={r.label}
          onChange={(e) => setR({ ...r, label: e.target.value })}
          className="w-full bg-transparent font-display text-xl font-extrabold outline-none"
        />
        <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-xs font-semibold">
          {isSeed ? "Original" : "AI draft"}
        </span>
      </div>
      {r.example_claim && <p className="mt-1 text-sm text-muted-foreground">From scan: “{r.example_claim}”</p>}

      <label className="mt-4 block text-xs font-semibold uppercase text-muted-foreground">Claim wording it matches (one per line)</label>
      <textarea
        rows={3}
        value={r.match.join("\n")}
        onChange={(e) => setR({ ...r, match: e.target.value.split("\n") })}
        className="mt-1 w-full rounded-2xl border border-input bg-background p-3 text-sm"
        placeholder={rule.match.length ? "" : "Uses a pattern match (original rule)"}
      />

      <label className="mt-3 block text-xs font-semibold uppercase text-muted-foreground">What it checks</label>
      <select
        value={r.check_type}
        onChange={(e) => setR({ ...r, check_type: e.target.value })}
        className="mt-1 w-full rounded-2xl border border-input bg-background p-3 text-sm"
      >
        {Object.entries(CHECK_LABELS).map(([k, v]) => (
          <option key={k} value={k}>{v}</option>
        ))}
      </select>

      {(r.check_type === "ingredient_present" || r.check_type === "subject_absent_or_flavour_only") && (
        <>
          <label className="mt-3 block text-xs font-semibold uppercase text-muted-foreground">{r.check_type === "ingredient_present" ? "Ingredient words that contradict it (one per line)" : "Spellings of the named ingredient (one per line)"}</label>
          <textarea
            rows={3}
            value={r.terms.join("\n")}
            onChange={(e) => setR({ ...r, terms: e.target.value.split("\n") })}
            className="mt-1 w-full rounded-2xl border border-input bg-background p-3 text-sm"
          />
        </>
      )}

      <label className="mt-3 block text-xs font-semibold uppercase text-muted-foreground">Note</label>
      <textarea
        rows={2}
        value={r.note}
        onChange={(e) => setR({ ...r, note: e.target.value })}
        className="mt-1 w-full rounded-2xl border border-input bg-background p-3 text-sm"
      />
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          Confidence
          <select
            value={r.confidence}
            onChange={(e) => setR({ ...r, confidence: e.target.value })}
            className="rounded-xl border border-input bg-background px-2 py-1"
          >
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={r.verify} onChange={(e) => setR({ ...r, verify: e.target.checked })} />
          Show "check the pack" note
        </label>
      </div>
      {err && <p className="mt-3 rounded-xl bg-secondary p-3 text-sm">{err}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          disabled={saving}
          onClick={() => commit("approved")}
          className="btn-press rounded-2xl bg-primary px-5 py-2 font-bold text-primary-foreground disabled:opacity-50"
        >
          {rule.status === "approved" ? "Save" : "Approve and go live"}
        </button>
        {rule.status !== "rejected" && (
          <button disabled={saving} onClick={() => commit("rejected")} className="rounded-2xl bg-secondary px-5 py-2 font-semibold">
            {rule.status === "approved" ? "Take offline" : "Reject"}
          </button>
        )}
        {rule.status === "rejected" && (
          <button disabled={saving} onClick={() => commit("draft")} className="rounded-2xl bg-secondary px-5 py-2 font-semibold">
            Move back to review
          </button>
        )}
      </div>
    </div>
  );
}

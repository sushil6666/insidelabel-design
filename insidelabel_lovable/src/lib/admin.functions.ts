import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

const CHECK_TYPES = [
  "added_sugar_present",
  "preservative_present",
  "subject_absent_or_flavour_only",
  "ingredient_present",
  "not_checkable",
] as const;

type Ctx = { supabase: any; userId: string };

async function assertAdmin(ctx: Ctx) {
  const { data, error } = await ctx.supabase.rpc("has_role", { _user_id: ctx.userId, _role: "admin" });
  if (error || !data) throw new Error("Only the admin can do this.");
}

export const getAdminStatus = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { data } = await context.supabase.rpc("has_role", { _user_id: context.userId, _role: "admin" });
    return { isAdmin: !!data };
  });

export const listClaimData = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context);
    const [rules, unmatched] = await Promise.all([
      context.supabase.from("claim_rules").select("*").order("created_at", { ascending: false }),
      context.supabase
        .from("unmatched_claims")
        .select("*")
        .eq("status", "new")
        .order("times_seen", { ascending: false })
        .limit(100),
    ]);
    if (rules.error) throw new Error(rules.error.message);
    if (unmatched.error) throw new Error(unmatched.error.message);
    return { rules: rules.data, unmatched: unmatched.data };
  });

const draftSchema = z.object({
  id: z.string().regex(/^[a-z0-9_]{2,60}$/),
  label: z.string().min(2).max(80),
  match: z.array(z.string().min(2).max(80)).min(1).max(12),
  check_type: z.enum(CHECK_TYPES),
  terms: z.array(z.string().min(2).max(60)).max(20),
  confidence: z.enum(["high", "medium", "low"]),
  verify: z.boolean(),
  note: z.string().max(600),
});

function draftPrompt(claims: string[], existing: string[]) {
  return `You draft rules for a deterministic food-label claim checker. It compares a front-of-pack claim ONLY against the ingredient list (no nutrition panel).
Existing rule ids: ${existing.join(", ")}.
Allowed check_type values:
- added_sugar_present: contradicted if a recognised added sugar is in the list (use for sugar claims).
- preservative_present: contradicted by any preservative (use for "no preservatives" style claims).
- subject_absent_or_flavour_only: for "made with X" / "real X" claims. Put the spellings of X in "terms" (e.g. ["whole wheat","wholewheat","atta","whole wheat flour"]); contradicted if none appear or only inside a flavouring.
- ingredient_present: contradicted if any of "terms" appears in an ingredient entry. Terms are lowercase ingredient words, e.g. "no palm oil" -> ["palm oil","palmolein","palm kernel"]; "no maida" -> ["maida","refined wheat flour"]. Include common label spellings.
- not_checkable: the claim depends on quantities or processes the ingredient list cannot show (e.g. "high protein", "rich in fibre", "baked not fried"). terms must be [].
For each claim below return one rule. "match" = lowercase phrase variants of the claim as printed on packs. Set verify true and explain in "note" when the ingredient list alone cannot fully prove a breach. Never write editorial or health advice. Do not use em dashes or en dashes.
Return ONLY JSON: {"rules":[{"source_claim":"...","id":"snake_case","label":"...","match":["..."],"check_type":"...","terms":["..."],"confidence":"high|medium|low","verify":true,"note":"..."}]}
Claims:
${claims.map((c) => `- ${c}`).join("\n")}`;
}

export const draftRules = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ ids: z.array(z.string().uuid()).min(1).max(10) }).parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const sb = context.supabase;
    const { data: rows, error } = await sb.from("unmatched_claims").select("id, claim").in("id", data.ids);
    if (error) throw new Error(error.message);
    if (!rows?.length) return { drafted: 0, failed: 0 };
    const { data: existing } = await sb.from("claim_rules").select("id");
    const existingIds = new Set<string>((existing ?? []).map((r: { id: string }) => r.id));

    const { streamAiText } = await import("./ai-text.server");
    const text = await streamAiText(draftPrompt(rows.map((r: { claim: string }) => r.claim), [...existingIds]));
    const m = text.match(/\{[\s\S]*\}/);
    if (!m) throw new Error("AI returned nothing usable. Try again.");
    const parsed = JSON.parse(m[0]) as { rules?: Array<Record<string, unknown>> };

    let drafted = 0;
    let failed = 0;
    for (const raw of parsed.rules ?? []) {
      const src = String(raw["source_claim"] ?? "").toLowerCase().trim();
      const row = rows.find((r: { claim: string }) => r.claim === src) ?? null;
      const ok = draftSchema.safeParse(raw);
      if (!ok.success || !row) {
        failed++;
        continue;
      }
      let id = ok.data.id;
      while (existingIds.has(id)) id = `${ok.data.id}_${Math.floor(Math.random() * 1000)}`;
      existingIds.add(id);
      const rule = ok.data;
      const { error: insErr } = await sb.from("claim_rules").insert({
        id,
        label: rule.label,
        match: rule.match.map((s) => s.toLowerCase()),
        check_type: rule.check_type,
        terms: rule.check_type === "not_checkable" ? [] : rule.terms.map((s) => s.toLowerCase()),
        confidence: rule.confidence,
        verify: rule.verify,
        note: rule.note.replace(/[\u2013\u2014]/g, ","),
        status: "draft",
        source: "ai",
        example_claim: row.claim,
      });
      if (insErr) {
        failed++;
        continue;
      }
      await sb.from("unmatched_claims").update({ status: "drafted", draft_rule_id: id }).eq("id", row.id);
      drafted++;
    }
    return { drafted, failed };
  });

const ruleEdit = z.object({
  id: z.string(),
  label: z.string().min(2).max(80),
  match: z.array(z.string().min(2).max(80)).max(20),
  check_type: z.enum(CHECK_TYPES),
  terms: z.array(z.string().min(2).max(60)).max(30),
  confidence: z.enum(["high", "medium", "low"]),
  verify: z.boolean(),
  note: z.string().max(1000),
  status: z.enum(["draft", "approved", "rejected"]),
});

export const saveRule = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => ruleEdit.parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    if (data.check_type === "ingredient_present" && !data.terms.length) {
      throw new Error("Add at least one ingredient word for this rule.");
    }
    const { id, ...rest } = data;
    const { error } = await context.supabase
      .from("claim_rules")
      .update({ ...rest, updated_at: new Date().toISOString() })
      .eq("id", id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

export const dismissClaim = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ id: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { error } = await context.supabase.from("unmatched_claims").update({ status: "dismissed" }).eq("id", data.id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

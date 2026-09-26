import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/integrations/supabase/types";
import type { ClaimRule } from "./engine/claims";
import claimRules from "./engine/data/claim_rules.json";

const FALLBACK = (claimRules as unknown as { rules: ClaimRule[] }).rules;

type Row = Database["public"]["Tables"]["claim_rules"]["Row"];

export function rowToRule(r: Row): ClaimRule {
  return {
    id: r.id,
    label: r.label,
    match: r.match,
    ...(r.match_regex ? { match_regex: r.match_regex } : {}),
    check: r.check_type,
    terms: r.terms,
    confidence: r.confidence,
    verify: r.verify,
    note: r.note,
  };
}

/** Approved rules from the database; falls back to the bundled table if unreachable. */
export async function loadApprovedRules(): Promise<ClaimRule[]> {
  try {
    const url = process.env["SUPABASE_URL"];
    const key = process.env["SUPABASE_PUBLISHABLE_KEY"];
    if (!url || !key) return FALLBACK;
    const sb = createClient<Database>(url, key, {
      auth: { persistSession: false, autoRefreshToken: false },
      global: {
        fetch: (input, init) => {
          const h = new Headers(init?.headers);
          if (key.startsWith("sb_") && h.get("Authorization") === `Bearer ${key}`) h.delete("Authorization");
          h.set("apikey", key);
          return fetch(input, { ...init, headers: h });
        },
      },
    });
    const { data, error } = await sb
      .from("claim_rules")
      .select("*")
      .eq("status", "approved")
      .order("created_at");
    if (error || !data?.length) {
      if (error) console.error("claim rules load failed", error.message);
      return FALLBACK;
    }
    return data.map(rowToRule);
  } catch (e) {
    console.error("claim rules load failed", e);
    return FALLBACK;
  }
}

/** Queue claims no rule recognised, so the admin can review them. Never throws. */
export async function recordUnmatched(claims: string[]): Promise<void> {
  const list = claims.map((c) => c.trim()).filter((c) => c.length >= 2 && c.length <= 120).slice(0, 20);
  if (!list.length) return;
  try {
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { error } = await supabaseAdmin.rpc("record_unmatched_claims", { _claims: list });
    if (error) console.error("record unmatched failed", error.message);
  } catch (e) {
    console.error("record unmatched failed", e);
  }
}

/**
 * InsideLabel validation engine. Port of core/engine.py.
 * Takes a raw ingredient list string and returns a layered verdict.
 * AI reads the label; these deterministic rules judge it.
 */
import { tokenize, extractIns, prefixBareIns } from "./tokenize";
import { classifyToken, type AdditiveRow, type NovaMarker, type Flag } from "./classify";
import { gradeFor, CONCERN_PENALTY } from "./scoring";
import novaData from "./data/nova_markers.json";
import additivesData from "./data/additives.json";
import normData from "./data/normalization.json";

export { tokenize, extractIns, prefixBareIns };
export type { Flag };

const ADDITIVES = additivesData.additives as unknown as AdditiveRow[];
const ADDITIVE_BY_INS: Record<string, AdditiveRow> = {};
for (const a of ADDITIVES) {
  if (a.class !== "note") ADDITIVE_BY_INS[a.ins] = a;
}

const SYNONYM_LOOKUP: Record<string, string> = {};
for (const [canonical, aliases] of Object.entries(normData.synonyms)) {
  SYNONYM_LOOKUP[canonical.toLowerCase()] = canonical;
  for (const al of aliases) SYNONYM_LOOKUP[al.toLowerCase()] = canonical;
}

const SUGAR_ALIASES = new Set(
  normData.sugar_aliases.added_sugar.map((s) => s.toLowerCase()),
);

const NOVA_LOOKUP: Record<string, NovaMarker> = {};
for (const m of novaData.markers as unknown as NovaMarker[]) {
  for (const al of m.aliases) NOVA_LOOKUP[al.toLowerCase()] = m;
}

// A 'low' additive counts only when it carries a flag naming an actual concern.
const LOW_PENALTY_FLAGS = new Set<string>(
  (additivesData._meta as { scoring?: { low_penalty_flags?: string[] } }).scoring
    ?.low_penalty_flags ?? [],
);

function penalty(flag: Flag): number {
  if (
    flag.type === "additive" &&
    flag.concern === "low" &&
    !flag.flags.some((f) => LOW_PENALTY_FLAGS.has(f))
  ) {
    return 0;
  }
  return CONCERN_PENALTY[flag.concern] ?? 0;
}

export interface Verdict {
  binary: "clean" | "mixed" | "ultra-processed";
  grade: string;
  score: number;
  nova_ultra_processed: boolean;
  hidden_sugar_names: string[];
  flags: Flag[];
  ingredient_count_parsed: number;
  needs_verification: string[];
}

/** Main entry point. rawIngredients: the ingredient list as one string. */
export function analyze(rawIngredients: string): Verdict {
  const tokens = tokenize(rawIngredients);

  const flags: Flag[] = [];
  const sugarHits: string[] = [];
  let novaTriggered = false;
  const seen = new Set<string>();

  for (const t of tokens) {
    if (SUGAR_ALIASES.has(t)) sugarHits.push(t);
    const f = classifyToken(t, SYNONYM_LOOKUP, ADDITIVE_BY_INS, NOVA_LOOKUP);
    if (f) {
      if (seen.has(f.matched_as)) continue;
      seen.add(f.matched_as);
      flags.push(f);
      if (f.nova_group4) novaTriggered = true;
    }
  }

  // ---- Layer 2: score ----
  let score = 100;
  for (const f of flags) score -= penalty(f);

  // multiple added-sugar aliases => hidden-sugar penalty
  if (new Set(sugarHits).size >= 2) score -= 8;

  score = Math.max(0, Math.min(100, score));
  let [letter, band] = gradeFor(score);

  // ---- Layer 3: binary (NOVA is definitional and overrides upward) ----
  if (novaTriggered && band === "clean") band = "mixed";
  const binary: Verdict["binary"] =
    novaTriggered || band === "ultra-processed"
      ? "ultra-processed"
      : band === "mixed"
        ? "mixed"
        : "clean";

  return {
    binary,
    grade: letter,
    score,
    nova_ultra_processed: novaTriggered,
    hidden_sugar_names: [...new Set(sugarHits)].sort(),
    flags: flags.sort(
      (a, b) => (CONCERN_PENALTY[b.concern] ?? 0) - (CONCERN_PENALTY[a.concern] ?? 0),
    ),
    ingredient_count_parsed: tokens.length,
    needs_verification: flags.filter((f) => f.verify).map((f) => f.matched_as),
  };
}

export const NORM = normData;
export const ADDITIVE_TABLE = ADDITIVE_BY_INS;

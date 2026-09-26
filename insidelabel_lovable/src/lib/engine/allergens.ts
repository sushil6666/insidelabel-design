/**
 * Avoid-list allergen check. Port of lenses/allergens.py.
 * Five states per allergen, strongest first:
 * contains > may_contain > uncertain > not_listed, plus cannot_confirm.
 * Hard rule: never say "free from" or "safe". Strongest negative: "isn't listed".
 */
import allergenData from "./data/allergens.json";

export const ALLERGEN_MIN_CONFIDENCE = 0.95;

export interface AllergenRow {
  code: string;
  label: string;
  short: string;
  fssai_mandatory?: boolean;
  aliases: string[];
  exclude?: string[];
  ambiguous?: string[];
  ambiguous_cleared_by?: string[];
  statement_words: string[];
  note?: string;
}

const ALLERGENS: Record<string, AllergenRow> = {};
for (const a of allergenData.allergens as unknown as AllergenRow[]) {
  ALLERGENS[a.code] = a;
}
const TRIGGERS: string[] = allergenData.cross_contact_triggers;
const NUT_WORDS = new Set(["nuts", "mixed nuts", "nut paste"]);
const SPECIFIC_NUTS = new Set([
  ...ALLERGENS["peanut"]!.aliases,
  ...ALLERGENS["tree_nuts"]!.aliases,
]);

const RANK: Record<string, number> = {
  contains: 4,
  may_contain: 3,
  uncertain: 2,
  not_listed: 1,
};

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function has(term: string, text: string): boolean {
  return new RegExp(`(?<![a-z0-9])${escapeRe(term)}(?![a-z0-9])`).test(text);
}

function stripExcluded(text: string, allergen: AllergenRow): string {
  for (const ex of [...(allergen.exclude ?? [])].sort((a, b) => b.length - a.length)) {
    text = text.replace(
      new RegExp(`(?<![a-z0-9])${escapeRe(ex)}(?![a-z0-9])`, "g"),
      " ",
    );
  }
  return text;
}

function splitStatement(statement: string): [string[], string[]] {
  const contains: string[] = [];
  const may: string[] = [];
  for (const sentence of statement.toLowerCase().split(/[.;\n]+/)) {
    const s = sentence.trim();
    if (!s) continue;
    const hits = TRIGGERS.map((t) => s.indexOf(t)).filter((i) => i >= 0);
    if (hits.length) {
      const i = Math.min(...hits);
      if (s.slice(0, i).trim()) contains.push(s.slice(0, i));
      may.push(s.slice(i));
    } else {
      contains.push(s);
    }
  }
  return [contains, may];
}

export type AllergenState =
  | "contains"
  | "may_contain"
  | "uncertain"
  | "not_listed"
  | "cannot_confirm";

export interface AllergenResult {
  code: string;
  state: AllergenState;
  evidence: string;
  statement_seen: boolean;
}

export function allergenText(r: AllergenResult, who = "your child"): string {
  const a = ALLERGENS[r.code]!;
  const { label, short } = a;
  const whose = who === "you" ? "your" : `${who}'s`;
  if (r.state === "contains") return `Contains ${short}. It's on ${whose} avoid list.`;
  if (r.state === "may_contain") return `The pack says it may contain ${short}.`;
  if (r.state === "uncertain") {
    const then = who === "you" ? "before you eat it" : `before giving it to ${who}`;
    return `We can't tell whether "${r.evidence}" comes from ${short}. Check with the brand ${then}.`;
  }
  if (r.state === "cannot_confirm") {
    return `We couldn't read the label clearly enough to check for ${short}. Please retake the ingredients photo.`;
  }
  let text = `${label[0]!.toUpperCase() + label.slice(1)} isn't listed in the ingredients`;
  if (r.statement_seen) text += " or the allergen line.";
  else text += `. We didn't see a "may contain" line in the photo, so check the pack.`;
  if (a.fssai_mandatory === false) {
    text += ` Brands don't have to declare ${short}, so this check is weaker.`;
  }
  return text;
}

export function checkAllergens(
  ingredients: string[],
  allergenStatement: string | null,
  codes: string[],
  confidence = 1.0,
  reliable = true,
): Record<string, AllergenResult> {
  for (const c of codes) {
    if (!ALLERGENS[c]) throw new Error(`unknown allergen code: ${c}`);
  }

  if (!reliable || !ingredients.length || confidence < ALLERGEN_MIN_CONFIDENCE) {
    return Object.fromEntries(
      codes.map((c) => [
        c,
        { code: c, state: "cannot_confirm", evidence: "", statement_seen: false },
      ]),
    );
  }

  const statementSeen = Boolean(allergenStatement && allergenStatement.trim());
  const [containsParts, mayParts] = statementSeen
    ? splitStatement(allergenStatement!)
    : [[], []];

  const results: Record<string, AllergenResult> = {};
  for (const code of codes) {
    const a = ALLERGENS[code]!;
    let best: AllergenResult = {
      code,
      state: "not_listed",
      evidence: "",
      statement_seen: statementSeen,
    };
    const consider = (state: AllergenState, evidence: string) => {
      if (RANK[state]! > RANK[best.state]!) {
        best = { code, state, evidence, statement_seen: statementSeen };
      }
    };

    // 1. Ingredient list.
    for (const tok of ingredients) {
      const low = stripExcluded(tok.toLowerCase(), a);
      if (a.aliases.some((al) => has(al, low))) {
        consider("contains", tok);
        continue;
      }
      for (const amb of a.ambiguous ?? []) {
        if (!has(amb, low)) continue;
        if (NUT_WORDS.has(amb) && [...SPECIFIC_NUTS].some((n) => has(n, low))) continue;
        if ((a.ambiguous_cleared_by ?? []).some((c) => has(c, low))) continue;
        consider("uncertain", tok);
      }
    }

    // 2. Printed allergen line.
    const words = a.statement_words;
    for (const part of containsParts) {
      const p = stripExcluded(part, a);
      if (words.some((w) => has(w, p))) consider("contains", part.trim());
      else if ((a.ambiguous ?? []).some((w) => NUT_WORDS.has(w) && has(w, p)))
        consider("uncertain", part.trim());
    }
    for (const part of mayParts) {
      const p = stripExcluded(part, a);
      if (
        words.some((w) => has(w, p)) ||
        (a.ambiguous ?? []).some((w) => NUT_WORDS.has(w) && has(w, p))
      ) {
        consider("may_contain", part.trim());
      }
    }

    results[code] = best;
  }
  return results;
}

export const ALLERGEN_TABLE = ALLERGENS;

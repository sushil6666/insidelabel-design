/**
 * Claim checker. Port of claims/checker.py.
 * Compares verbatim front-of-pack claims against the engine's output and
 * returns contradicting ingredient facts as pairs. No editorial language.
 */
import { tokenize, extractIns, type Verdict } from "./engine";
import normData from "./data/normalization.json";
import claimRules from "./data/claim_rules.json";
import additivesData from "./data/additives.json";

export interface ClaimRule {
  id: string;
  terms?: string[];
  label: string;
  match?: string[];
  match_regex?: string;
  check: string;
  confidence: string;
  verify: boolean;
  note: string;
}

const RULES = claimRules as unknown as {
  rules: ClaimRule[];
  added_sugar_adjacent: string[];
  preservative_named_without_ins: string[];
  real_subject_synonyms: Record<string, string[]>;
  flavour_carrier_words: string[];
};

const ADDITIVES = additivesData.additives as unknown as Array<{
  ins: string;
  name: string;
  class: string;
}>;
const ADDITIVE_BY_INS: Record<string, (typeof ADDITIVES)[number]> = {};
for (const a of ADDITIVES) if (a.class !== "note") ADDITIVE_BY_INS[a.ins] = a;
const PRESERVATIVE_INS = new Set(
  Object.entries(ADDITIVE_BY_INS)
    .filter(([, a]) => a.class === "preservative")
    .map(([ins]) => ins),
);

const ADJACENT = new Set(RULES.added_sugar_adjacent);
const ADDED_SUGAR_DIRECT = new Set(
  normData.sugar_aliases.added_sugar
    .map((s) => s.toLowerCase())
    .filter((s) => !ADJACENT.has(s)),
);
const FLAVOUR_WORDS = RULES.flavour_carrier_words;
const NAMED_PRESERVATIVES = RULES.preservative_named_without_ins;

function norm(text: string): string {
  let t = text.toLowerCase().replace(/\*/g, " ");
  t = t.replace(/[^a-z0-9%\s-]/g, " ");
  return t.replace(/\s+/g, " ").trim();
}

function matchRule(claimText: string, rules: ClaimRule[]): [ClaimRule | null, string | null] {
  const n = norm(claimText);
  for (const rule of rules) {
    for (const phrase of rule.match ?? []) {
      if (n.includes(phrase)) return [rule, null];
    }
    if (rule.match_regex) {
      // Data tables use Python-style named groups (?P<name>); JS needs (?<name>).
      const m = new RegExp(rule.match_regex.replace(/\(\?P</g, "(?<")).exec(n);
      if (m) return [rule, (m.groups?.["subject"] ?? "").trim()];
    }
  }
  return [null, null];
}

export interface ClaimFact {
  fact: string;
  evidence: string | null;
  evidence_type: string;
  relation?: string;
  reason?: string;
}

export interface CheckedClaim {
  claim: string;
  rule_id: string;
  rule_label: string;
  subject: string | null;
  contradicted: boolean;
  contradicted_by: ClaimFact[];
  confidence: string;
  verify: boolean;
  verify_note?: string;
  adjacent_facts?: ClaimFact[];
}

export interface ClaimCheckResult {
  status: "checked" | "not_checked";
  reason: string | null;
  claims_examined: number;
  checked: CheckedClaim[];
  unmatched_claims: string[];
}

type CheckFn = (result: Verdict, tokens: string[], subject: string | null) => ClaimFact[];

const checkAddedSugar: CheckFn = (result) => {
  const facts: ClaimFact[] = [];
  for (const name of result.hidden_sugar_names) {
    if (ADDED_SUGAR_DIRECT.has(name)) {
      facts.push({
        fact: `Ingredient list contains ${name}.`,
        evidence: name,
        evidence_type: "ingredient",
      });
    }
  }
  return facts;
};

function adjacentSugarNotes(result: Verdict): ClaimFact[] {
  const notes: ClaimFact[] = [];
  for (const name of result.hidden_sugar_names) {
    if (ADJACENT.has(name)) {
      notes.push({
        fact: `Ingredient list contains ${name}.`,
        evidence: name,
        evidence_type: "ingredient",
        relation: "adjacent",
        reason:
          "Counted by the hidden-sugar heuristic but not a sugar under the " +
          "added-sugar definition. Reported separately, not as a contradiction.",
      });
    }
  }
  return notes;
}

const checkPreservative: CheckFn = (result, tokens) => {
  const facts: ClaimFact[] = [];
  const seen = new Set<string>();
  for (const f of result.flags) {
    const ins = extractIns(f.matched_as);
    if (!ins) continue;
    if (PRESERVATIVE_INS.has(ins) && !seen.has(ins)) {
      seen.add(ins);
      facts.push({
        fact: `Ingredient list contains INS ${ins} (${ADDITIVE_BY_INS[ins]!.name}), a preservative.`,
        evidence: f.matched_as,
        evidence_type: "additive",
      });
    }
  }
  for (const tok of tokens) {
    for (const named of NAMED_PRESERVATIVES) {
      if (tok.includes(named) && !seen.has(named)) {
        seen.add(named);
        facts.push({
          fact: `Ingredient list contains ${named}, a preservative.`,
          evidence: tok,
          evidence_type: "ingredient",
        });
      }
    }
  }
  return facts;
};

const checkRealSubject: CheckFn = (_result, tokens, subject) => {
  if (!subject) return [];
  const s = subject.trim();
  const synonyms = RULES.real_subject_synonyms[s] ?? [s];
  const hits = tokens.filter((t) => synonyms.some((syn) => t.includes(syn)));

  if (!hits.length) {
    return [
      {
        fact: `'${s}' does not appear in the ingredient list.`,
        evidence: null,
        evidence_type: "absence",
      },
    ];
  }
  const flavourOnly = hits.every((h) => FLAVOUR_WORDS.some((w) => h.includes(w)));
  if (flavourOnly) {
    return [
      {
        fact: `'${s}' appears in the ingredient list only as: ${hits.join(", ")}.`,
        evidence: hits[0] ?? null,
        evidence_type: "flavouring",
      },
    ];
  }
  return [];
};

// Generic: contradicted when any listed term appears in an ingredient entry
// (e.g. "no palm oil" -> terms ["palm oil", "palmolein"]).
function makeIngredientPresent(terms: string[]): CheckFn {
  return (_result, tokens) => {
    const facts: ClaimFact[] = [];
    const seen = new Set<string>();
    for (const tok of tokens) {
      for (const term of terms) {
        const t = term.toLowerCase().trim();
        if (t && tok.includes(t) && !seen.has(t)) {
          seen.add(t);
          facts.push({ fact: `Ingredient list contains ${tok}.`, evidence: tok, evidence_type: "ingredient" });
        }
      }
    }
    return facts;
  };
}

// Phrase-matched "made with X" rule: the subject's spellings come from the rule's terms.
function makeSubjectTerms(label: string, terms: string[]): CheckFn {
  return (_result, tokens) => {
    const hits = tokens.filter((t) => terms.some((syn) => t.includes(syn)));
    if (!hits.length) {
      return [{ fact: `'${terms[0]}' does not appear in the ingredient list.`, evidence: null, evidence_type: "absence" }];
    }
    if (hits.every((h) => FLAVOUR_WORDS.some((w) => h.includes(w)))) {
      return [{ fact: `'${terms[0]}' appears in the ingredient list only as: ${hits.join(", ")}.`, evidence: hits[0] ?? null, evidence_type: "flavouring" }];
    }
    void label;
    return [];
  };
}

const CHECKS: Record<string, CheckFn> = {
  not_checkable: () => [],
  added_sugar_present: checkAddedSugar,
  preservative_present: checkPreservative,
  subject_absent_or_flavour_only: checkRealSubject,
};

export function checkClaims(
  frontClaims: string[],
  rawIngredients: string,
  result: Verdict,
  frontStatus: "read" | "not_provided" | "unreadable" | "pairing_unverified" | "ingredient_read_uncertain" = "read",
  rules: ClaimRule[] = RULES.rules,
): ClaimCheckResult {
  if (frontStatus !== "read") {
    return {
      status: "not_checked",
      reason:
        frontStatus === "pairing_unverified" || frontStatus === "ingredient_read_uncertain"
          ? frontStatus
          : `front_${frontStatus}`,
      claims_examined: 0,
      checked: [],
      unmatched_claims: [...(frontClaims ?? [])],
    };
  }

  const tokens = tokenize(rawIngredients);
  const checked: CheckedClaim[] = [];
  const unmatched: string[] = [];

  for (const claim of frontClaims ?? []) {
    const [rule, subject] = matchRule(claim, rules);
    if (!rule) {
      unmatched.push(claim);
      continue;
    }
    const terms = (rule.terms ?? []).map((t) => t.toLowerCase().trim()).filter(Boolean);
    const fn: CheckFn | undefined =
      rule.check === "ingredient_present"
        ? makeIngredientPresent(terms)
        : rule.check === "subject_absent_or_flavour_only" && !subject && terms.length
          ? makeSubjectTerms(rule.label, terms)
          : CHECKS[rule.check];
    if (!fn) {
      unmatched.push(claim);
      continue;
    }
    const facts = fn(result, tokens, subject);
    const entry: CheckedClaim = {
      claim,
      rule_id: rule.id,
      rule_label: rule.label,
      subject: subject || null,
      contradicted: facts.length > 0,
      contradicted_by: facts,
      confidence: rule.confidence,
      verify: rule.verify,
    };
    if (rule.verify) entry.verify_note = rule.note;
    if (rule.check === "added_sugar_present") {
      const adjacent = adjacentSugarNotes(result);
      if (adjacent.length) entry.adjacent_facts = adjacent;
    }
    checked.push(entry);
  }

  return {
    status: "checked",
    reason: null,
    claims_examined: (frontClaims ?? []).length,
    checked,
    unmatched_claims: unmatched,
  };
}

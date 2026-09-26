/**
 * Ingredient tokenization and INS/E-number extraction.
 * Port of core/tokenize.py - the only INS parser in the app.
 */
import normData from "./data/normalization.json";

const CLASS_WORDS: string[] = normData.additive_class_words.words;

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const CLASS_RE = new RegExp(
  "(?<![a-z])(?:" +
    [...CLASS_WORDS]
      .sort((a, b) => b.length - a.length)
      .map((w) => escapeRe(w).replace(/\\ /g, "\\s+"))
      .join("|") +
    ")(?![a-z])",
  "gi",
);

// INS numbers run 100-1521, so 3 or 4 digits, plus an optional single-letter
// suffix (150d, 472e). A spaced suffix ("160 a(ii)") is accepted for a-f only.
const INS_NUMBER = "(\\d{3,4}(?:[a-z](?![a-z])|\\s[a-f](?![a-z]))?)(?![0-9])";

// A bare additive number, not already carrying an INS/E prefix.
const BARE_NUM = new RegExp(
  "(?<![a-z0-9])(?<!ins )(?<!ins)(?<!e)" + INS_NUMBER,
  "gi",
);

// An explicit INS/E number. The prefix must be a word of its own.
const INS_RE = new RegExp(
  "(?<![a-z])(?:ins|e)[\\s\\-.]*?" + INS_NUMBER,
  "i",
);

// A token that is nothing but an additive number.
const WHOLE_NUM = /^(\d{3,4}[a-f]?)$/;

const OPEN = "([{";
const CLOSE: Record<string, string> = { "(": ")", "[": "]", "{": "}" };

function balancedSpan(text: string, openIdx: number): number | null {
  const opener = text[openIdx]!;
  const closer = CLOSE[opener]!;
  let depth = 0;
  for (let i = openIdx; i < text.length; i++) {
    if (text[i] === opener) depth++;
    else if (text[i] === closer) {
      depth--;
      if (depth === 0) return i + 1;
    }
  }
  return null;
}

/**
 * Rewrite bare additive numbers as explicit INS numbers, but ONLY inside a
 * bracket introduced by an additive class word.
 */
export function prefixBareIns(raw: string): string {
  const out: string[] = [];
  let pos = 0;
  CLASS_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CLASS_RE.exec(raw)) !== null) {
    if (m.index < pos) continue;
    let j = m.index + m[0].length;
    while (j < raw.length && " \t:.-".includes(raw[j]!)) j++;
    if (j >= raw.length || !OPEN.includes(raw[j]!)) continue;
    const end = balancedSpan(raw, j);
    if (end === null) continue;
    const inner = raw.slice(j + 1, end - 1);
    if (!/\d{3}/.test(inner)) continue;
    out.push(raw.slice(pos, j + 1));
    BARE_NUM.lastIndex = 0;
    out.push(inner.replace(BARE_NUM, "INS $1"));
    pos = end - 1;
  }
  out.push(raw.slice(pos));
  return out.join("");
}

/** Split a raw ingredient string into candidate ingredient tokens. */
export function tokenize(raw: string): string[] {
  raw = raw.replace(/\ballergens?\b[\s\S]*$/i, "");
  raw = prefixBareIns(raw);

  // A spaced "&" separates entries; an unspaced one is part of a name.
  const parts = raw.split(/[,;.\n]|\s+&\s+/);
  const tokens: string[] = [];

  for (const p of parts) {
    const inner: string[] = [];
    const innerRe = /[\(\[]([^\)\]]*)[\)\]]/g;
    let im: RegExpExecArray | null;
    while ((im = innerRe.exec(p)) !== null) inner.push(im[1]!);
    const base = p.replace(/[\(\[][^\)\]]*[\)\]]/g, "");

    for (const chunk of [base, ...inner]) {
      for (const sub of chunk.split(/[,;]|\s+&\s+/)) {
        let t = sub.trim().toLowerCase();
        t = t.replace(/\s+/g, " ");
        if (t && !/^[\d\s%.]+$/.test(t)) tokens.push(t);
      }
    }
  }
  return tokens;
}

/** If token contains an INS/E number, return the bare number string. */
export function extractIns(token: string): string | null {
  const m = INS_RE.exec(token);
  if (m) return m[1]!.toLowerCase().replace(" ", "");
  const m2 = WHOLE_NUM.exec(token.trim());
  if (m2) return m2[1]!.toLowerCase();
  return null;
}

/** Every INS number the engine would read in `text`. */
export function insNumbers(text: string | string[]): Set<string> {
  const joined = typeof text === "string" ? text : (text ?? []).join(", ");
  const out = new Set<string>();
  for (const t of tokenize(joined)) {
    const i = extractIns(t);
    if (i) out.add(i);
  }
  return out;
}

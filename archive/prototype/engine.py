"""
Inside Label — validation engine (v0.1)
========================================
Segment-blind core. Takes a raw ingredient list (as a string, e.g. straight
from OCR) and returns a layered verdict:

    Layer 1  per-ingredient flags   (source of truth, fully traceable)
    Layer 2  score 0-100 + grade    (derived from Layer 1)
    Layer 3  binary clean/UPF label (threshold on the score)

Design rules (deliberate, not accidental):
  * The engine states INGREDIENT FACTS only. It never says "safe for X".
    Segment lenses live in a layer ABOVE this and are not implemented here.
  * Every verdict traces to a specific rule/table row. No "the AI decided".
  * NOVA Group-4 markers are DEFINITIONAL: one marker => ultra-processed,
    regardless of score. Score adds nuance; it does not overturn NOVA.
  * Data lives in /data/*.json so any future app (web, PWA, native) calls the
    same core. This file is logic; the moat is the data.

This is a VALIDATION prototype: run it on real ingredient lists and check
whether the verdicts hold up before investing in the full engine or any app.
"""

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ----------------------------------------------------------------------------
# Load tables
# ----------------------------------------------------------------------------
def _load(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


NOVA = _load("nova_markers.json")
ADDITIVES = _load("additives.json")
NORM = _load("normalization.json")

# Build fast lookups
_ADDITIVE_BY_INS = {a["ins"]: a for a in ADDITIVES["additives"] if a.get("class") != "note"}

# alias -> canonical synonym key
_SYNONYM_LOOKUP = {}
for canonical, aliases in NORM["synonyms"].items():
    _SYNONYM_LOOKUP[canonical.lower()] = canonical
    for al in aliases:
        _SYNONYM_LOOKUP[al.lower()] = canonical

# sugar aliases set
_SUGAR_ALIASES = set(s.lower() for s in NORM["sugar_aliases"]["added_sugar"])

# nova alias -> marker
_NOVA_LOOKUP = {}
for m in NOVA["markers"]:
    for al in m["aliases"]:
        _NOVA_LOOKUP[al.lower()] = m

# Class words that make a bracket an additive bracket. Sourced from
# normalization.json so the list stays in the data layer; the fallback keeps
# the engine working against an older table.
_CLASS_WORDS = NORM.get("additive_class_words", {}).get("words", [
    "emulsifier", "emulsifiers", "preservative", "preservatives",
    "stabiliser", "stabilisers", "stabilizer", "stabilizers",
    "acidity regulator", "acidity regulators", "raising agent", "raising agents",
    "colour", "colours", "color", "colors", "flavour enhancer", "flavour enhancers",
    "sweetener", "sweeteners", "antioxidant", "antioxidants", "thickener", "thickeners",
])
# Longest-first so "acidity regulators" wins over "acid".
_CLASS_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(
        re.escape(w).replace(r"\ ", r"\s+") for w in sorted(_CLASS_WORDS, key=len, reverse=True)
    ) + r")(?![a-z])",
    re.IGNORECASE,
)
# A bare additive number: 3 digits, optional letter suffix, not already carrying
# an INS/E prefix.
_BARE_NUM = re.compile(r"(?<![a-z0-9])(?<!ins )(?<!ins)(?<!e)(\d{3}[a-z]?)(?![0-9])", re.IGNORECASE)


def _balanced_span(text, open_idx):
    """Return the index just past the bracket group opening at open_idx, or None."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def prefix_bare_ins(raw):
    """
    Rewrite bare additive numbers as explicit INS numbers, but ONLY inside a
    bracket introduced by an additive class word.

    Indian labels overwhelmingly print additives as bare numbers in a class
    bracket -- "ACIDITY REGULATORS (330, 331(iii))", "PRESERVATIVE (211)" --
    with no INS or E prefix anywhere.

    Doing this by context rather than by shape is the whole point. 200, 250 and
    500 are all real additives in the table AND all common quantities on a
    pack, so a rule that promoted every 3-digit token would read "200 ml" as
    sorbic acid and "250 kcal" as sodium nitrite. The class word is the only
    thing that distinguishes the two, so no class word means no rewrite.

    Returns the rewritten string. Idempotent: numbers already prefixed with
    INS or E are left alone.
    """
    out = []
    pos = 0
    for m in _CLASS_RE.finditer(raw):
        if m.start() < pos:
            continue
        j = m.end()
        while j < len(raw) and raw[j] in " \t:.-":
            j += 1
        if j >= len(raw) or raw[j] != "(":
            continue
        end = _balanced_span(raw, j)
        if end is None:
            continue
        inner = raw[j + 1:end - 1]
        if not re.search(r"\d{3}", inner):
            continue
        out.append(raw[pos:j + 1])
        out.append(_BARE_NUM.sub(r"INS \1", inner))
        pos = end - 1
    out.append(raw[pos:])
    return "".join(out)


# concern -> penalty weight (tunable — this is a values choice, document it)
_CONCERN_PENALTY = {"none": 0, "low": 4, "moderate": 12, "high": 25}

# grade bands on the 0-100 score
_GRADE_BANDS = [
    (85, "A", "clean"),
    (70, "B", "clean"),
    (50, "C", "mixed"),
    (30, "D", "ultra-processed"),
    (0,  "E", "ultra-processed"),
]


# ----------------------------------------------------------------------------
# Tokenize + normalize
# ----------------------------------------------------------------------------
def tokenize(raw):
    """Split a raw ingredient string into candidate ingredient tokens."""
    # drop everything after common noise headers
    raw = re.sub(r"(?i)\ballergen[s]?\b.*$", "", raw)
    # promote bare additive numbers inside class brackets to explicit INS
    # numbers, so they survive the all-numeric noise filter below
    raw = prefix_bare_ins(raw)
    # split on commas, semicolons, periods, and bracket boundaries
    parts = re.split(r"[,;.\n]", raw)
    tokens = []
    for p in parts:
        # pull nested bracket contents out as their own tokens too
        inner = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", p)
        base = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", p)
        for chunk in [base] + inner:
            for sub in re.split(r"[,;]", chunk):
                t = sub.strip().lower()
                t = re.sub(r"\s+", " ", t)
                if t and not re.fullmatch(r"[\d\s%.]+", t):
                    tokens.append(t)
    return tokens


def extract_ins(token):
    """If token contains an INS/E number, return the bare number string."""
    m = re.search(r"(?:ins|e)[\s\-.]*?(\d{3}[a-z]?)", token, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    # bare 3-digit number as its own token (e.g. "621")
    m2 = re.fullmatch(r"(\d{3}[a-z]?)", token.strip())
    if m2:
        return m2.group(1).lower()
    return None


def normalize(token):
    """Return canonical form of a token via synonym table (best effort)."""
    if token in _SYNONYM_LOOKUP:
        return _SYNONYM_LOOKUP[token]
    return token


# ----------------------------------------------------------------------------
# Classify one token
# ----------------------------------------------------------------------------
def classify_token(token):
    """Return a flag dict for a token, or None if unremarkable."""
    canonical = normalize(token)

    # 1) INS-number additive match (strongest signal)
    ins = extract_ins(token)
    if ins and ins in _ADDITIVE_BY_INS:
        a = _ADDITIVE_BY_INS[ins]
        return {
            "ingredient": token,
            "matched_as": f"INS {ins} ({a['name']})",
            "type": "additive",
            "concern": a["concern"],
            "why": a["why"],
            "sources": a["sources"],
            "flags": a.get("flags", []),
            "verify": a.get("verify", False),
            "nova_group4": _is_nova(token, canonical),
        }

    # 2) named additive match (e.g. "aspartame" without a number)
    for a in _ADDITIVE_BY_INS.values():
        name_l = a["name"].lower()
        if canonical == name_l or token == name_l or canonical in name_l.split(" ("):
            return {
                "ingredient": token,
                "matched_as": f"{a['name']} (INS {a['ins']})",
                "type": "additive",
                "concern": a["concern"],
                "why": a["why"],
                "sources": a["sources"],
                "flags": a.get("flags", []),
                "verify": a.get("verify", False),
                "nova_group4": _is_nova(token, canonical),
            }

    # 3) NOVA-only marker (ultra-processing signal without a specific additive row)
    marker = _nova_marker(token, canonical)
    if marker:
        return {
            "ingredient": token,
            "matched_as": f"NOVA marker: {marker['name']}",
            "type": "nova_marker",
            "concern": "moderate" if marker["category"] != "cosmetic_additive" else "low",
            "why": f"Ultra-processing marker ({marker['category'].replace('_', ' ')}). "
                   f"Rarely used in home cooking; signals industrial formulation.",
            "sources": ["NOVA"],
            "flags": ["nova_group4_marker", marker["category"]],
            "verify": False,
            "nova_group4": True,
        }

    return None


def _nova_marker(token, canonical):
    for key in (token, canonical):
        if key in _NOVA_LOOKUP:
            return _NOVA_LOOKUP[key]
    # substring match for multiword markers
    for al, m in _NOVA_LOOKUP.items():
        if al in token:
            return m
    return None


def _is_nova(token, canonical):
    return _nova_marker(token, canonical) is not None


# ----------------------------------------------------------------------------
# Score + grade + binary
# ----------------------------------------------------------------------------
def grade_for(score):
    for threshold, letter, band in _GRADE_BANDS:
        if score >= threshold:
            return letter, band
    return "E", "ultra-processed"


def analyze(raw_ingredients):
    """Main entry point. raw_ingredients: str. Returns the layered verdict."""
    tokens = tokenize(raw_ingredients)

    flags = []
    sugar_hits = []
    nova_triggered = False
    seen = set()

    for t in tokens:
        if t in _SUGAR_ALIASES:
            sugar_hits.append(t)
        f = classify_token(t)
        if f:
            key = f["matched_as"]
            if key in seen:
                continue
            seen.add(key)
            flags.append(f)
            if f.get("nova_group4"):
                nova_triggered = True

    # ---- Layer 2: score ----
    score = 100
    for f in flags:
        score -= _CONCERN_PENALTY.get(f["concern"], 0)

    # multiple added-sugar aliases => hidden-sugar penalty (marketing obfuscation)
    if len(set(sugar_hits)) >= 2:
        score -= 8

    score = max(0, min(100, score))
    letter, band = grade_for(score)

    # ---- Layer 3: binary (NOVA is definitional and overrides upward) ----
    if nova_triggered and band == "clean":
        # a product with a NOVA Group-4 marker cannot be labelled "clean"
        band = "mixed"
    binary = "ultra-processed" if (nova_triggered or band == "ultra-processed") else \
             ("mixed" if band == "mixed" else "clean")

    return {
        "binary": binary,
        "grade": letter,
        "score": score,
        "nova_ultra_processed": nova_triggered,
        "hidden_sugar_names": sorted(set(sugar_hits)),
        "flags": sorted(flags, key=lambda x: _CONCERN_PENALTY.get(x["concern"], 0), reverse=True),
        "ingredient_count_parsed": len(tokens),
        "needs_verification": [f["matched_as"] for f in flags if f.get("verify")],
    }


# ----------------------------------------------------------------------------
# Pretty printer for the CLI
# ----------------------------------------------------------------------------
def render(result):
    band_symbol = {"clean": "✓ CLEAN", "mixed": "~ MIXED", "ultra-processed": "✗ ULTRA-PROCESSED"}
    out = []
    out.append("=" * 60)
    out.append(f"  VERDICT: {band_symbol.get(result['binary'], result['binary'])}"
               f"   |   Grade {result['grade']}   |   Score {result['score']}/100")
    out.append("=" * 60)
    if result["nova_ultra_processed"]:
        out.append("  ⚑ Contains NOVA Group-4 marker(s) → ultra-processed by definition")
    if result["hidden_sugar_names"]:
        out.append(f"  ⚑ Sugar appears under {len(result['hidden_sugar_names'])} name(s): "
                   f"{', '.join(result['hidden_sugar_names'])}")
    out.append("")
    out.append("  Flagged ingredients (most concerning first):")
    if not result["flags"]:
        out.append("    (none flagged — either genuinely clean or not in starter DB)")
    for f in result["flags"]:
        tag = {"high": "HIGH", "moderate": "MOD ", "low": "LOW ", "none": "OK  "}[f["concern"]]
        vflag = "  [VERIFY vs FSSAI]" if f.get("verify") else ""
        out.append(f"    [{tag}] {f['matched_as']}{vflag}")
        out.append(f"           {f['why']}")
        out.append(f"           sources: {', '.join(f['sources'])}")
    if result["needs_verification"]:
        out.append("")
        out.append("  ⚠ These rows carry legal exposure — verify against live FSSAI")
        out.append("    notifications before any public 'banned/permitted' claim:")
        for v in result["needs_verification"]:
            out.append(f"      - {v}")
    out.append("=" * 60)
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
        print(render(analyze(raw)))
    else:
        # built-in demo on realistic Indian product ingredient lists
        samples = {
            "Cream biscuit (typical)":
                "Refined wheat flour (maida), Sugar, Edible vegetable oil (palm), "
                "Invert syrup, Milk solids, Cocoa solids, Emulsifiers (INS 322, INS 471), "
                "Raising agents (INS 500(ii), INS 503(ii)), Salt, "
                "Added flavours (natural and artificial), INS 621",
            "Instant noodles masala":
                "Noodles: Refined wheat flour, Palm oil, Salt, Thickeners (INS 508, INS 412), "
                "Acidity regulators (INS 501, INS 500). "
                "Tastemaker: Sugar, Iodised salt, Hydrolysed vegetable protein, "
                "Flavour enhancers (INS 635, INS 621), Spices, Maltodextrin, "
                "Colour (INS 150d)",
            "Plain roasted peanuts":
                "Peanuts, Salt",
            "Diet cola":
                "Carbonated water, Caramel colour (INS 150d), Acidity regulators (INS 338, INS 331), "
                "Sweeteners (INS 951, INS 950), Preservative (INS 211), Caffeine, "
                "Added flavours (natural and artificial)",
        }
        for name, ing in samples.items():
            print(f"\n\n### {name}")
            print(f"Ingredients: {ing}\n")
            print(render(analyze(ing)))

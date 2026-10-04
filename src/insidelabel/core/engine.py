"""
Inside Label - validation engine (v0.1)
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

from .tokenize import prefix_bare_ins, tokenize, extract_ins, ins_numbers, split_entries  # noqa: F401  (re-exported)
from .normalize import normalize
from .classify import classify_token, make_nova_helpers
from .scoring import grade_for, CONCERN_PENALTY, GRADE_BANDS

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))


# ----------------------------------------------------------------------------
# Load tables
# ----------------------------------------------------------------------------
def _load(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


NOVA = _load("nova_markers.json")
ADDITIVES = _load("additives.json")
NORM = _load("normalization.json")
NOTES = _load("ingredient_notes.json")["rows"]

# Build fast lookups
_ADDITIVE_BY_INS = {a["ins"]: a for a in ADDITIVES["additives"] if a.get("class") != "note"}


def source_names(codes):
    """The plain words for an additive row's `sources` codes, for a card's source line.
    The codes ("SOUTHAMPTON", "CODEX") are table keys and never reach a user."""
    shown = ADDITIVES["_meta"]["sources_shown"]
    return ", ".join(shown.get(c, c) for c in codes)

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

# INS parsing (class words, bare numbers, prefix_bare_ins) lives only in
# tokenize.py. It used to be duplicated here, and the copies could drift.

# concern -> penalty weight (tunable - this is a values choice, document it)
_CONCERN_PENALTY = CONCERN_PENALTY
_GRADE_BANDS = GRADE_BANDS

_nova_marker, _is_nova = make_nova_helpers(_NOVA_LOOKUP)

# A 'low' additive counts only when it carries a flag naming an actual concern
# (additives.json _meta.scoring). Class-only flags ("emulsifier") score 0.
_LOW_PENALTY_FLAGS = set(ADDITIVES["_meta"].get("scoring", {}).get("low_penalty_flags", []))


def _penalty(flag):
    if (flag["type"] == "additive" and flag["concern"] == "low"
            and not _LOW_PENALTY_FLAGS.intersection(flag.get("flags", []))):
        return 0
    return _CONCERN_PENALTY.get(flag["concern"], 0)


# ----------------------------------------------------------------------------
# Score + grade + binary
# ----------------------------------------------------------------------------

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
        f = classify_token(
            t,
            _SYNONYM_LOOKUP,
            _ADDITIVE_BY_INS,
            _NOVA_LOOKUP,
        )
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
        score -= _penalty(f)

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
# D-132: ingredients worth knowing (data/ingredient_notes.json)
# ----------------------------------------------------------------------------
# Information only: nothing here feeds the score, the band or the headline.
# Matching is by whole words in each entry of the list as printed, so a note
# can say where the ingredient sits ("listed 1st"); INS numbers are read by the
# one parser (tokenize.ins_numbers, D-099).

def _plain(text):
    """Lower case, brackets and punctuation as spaces: 'Wheat flour (refined)' -> 'wheat flour refined'."""
    return re.sub(r"\s+", " ", re.sub(r"[()\[\]{}.,;:*]", " ", (text or "").lower())).strip()


def _has_word(name, text):
    return re.search(r"(?<![a-z])" + re.escape(_plain(name)) + r"(?![a-z])", text) is not None


def _is_only(names, entry):
    """'unnamed': the entry is just this name, with nothing in brackets to name it."""
    if any(c in entry for c in "([{"):
        return False
    bare = re.sub(r"[\d.%]+", " ", _plain(entry))
    bare = re.sub(r"\s+", " ", bare).strip()
    return bare in {_plain(n) for n in names}


def _note_matches(row, entry):
    text = _plain(entry)
    if any(_has_word(x, text) for x in row.get("exclude", [])):
        return False
    if row.get("position_rule") == "unnamed":
        return _is_only(row["names"], entry)
    if any(_has_word(n, text) for n in row.get("names", [])):
        return True
    nums = ins_numbers(entry) if (row.get("ins") or row.get("conditional")) else set()
    if nums & set(row.get("ins", [])):
        return True
    for c in row.get("conditional", []):
        if any(_has_word(w, text) for w in c["when_entry_has"]):
            if any(_has_word(n, text) for n in c.get("names", [])) or nums & set(c.get("ins", [])):
                return True
    return False


def ingredient_notes(entries):
    """
    D-132: which ingredient_notes.json rows this list has, and where.
    entries: the ingredient list as printed (a list of entries), or a raw string,
    split the way the tokenizer splits it. Returns one hit per row, in the
    table's order: {"id", "positions" (1-based), "entries" (as printed)}.
    Rows with no names (the sugar row, which adds to the sugar answer) never match.
    """
    if isinstance(entries, str):
        entries = split_entries(entries)
    hits = []
    for row in NOTES:
        found = [(i, e) for i, e in enumerate(entries or [], start=1) if _note_matches(row, e)]
        if found:
            hits.append({"id": row["id"], "positions": [i for i, _ in found], "entries": [e for _, e in found]})
    return hits


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
        out.append("    (none flagged - either genuinely clean or not in starter DB)")
    for f in result["flags"]:
        tag = {"high": "HIGH", "moderate": "MOD ", "low": "LOW ", "none": "OK  "}[f["concern"]]
        vflag = "  [VERIFY vs FSSAI]" if f.get("verify") else ""
        out.append(f"    [{tag}] {f['matched_as']}{vflag}")
        out.append(f"           {f['why']}")
        out.append(f"           sources: {', '.join(f['sources'])}")
    if result["needs_verification"]:
        out.append("")
        out.append("  ⚠ These rows carry legal exposure - verify against live FSSAI")
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

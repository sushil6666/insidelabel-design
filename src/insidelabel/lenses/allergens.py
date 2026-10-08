#!/usr/bin/env python3
"""
allergens.py - avoid-list allergen check (D-071, D-072).

Reads two things prompt.py already returns, so no prompt change is needed:
  - ingredients          (verbatim entries, printed order)
  - allergen_statement   (the printed "Contains ... / May contain ..." line, or None)

Five states per allergen, strongest first:
  contains > may_contain > uncertain > not_listed,  plus cannot_confirm.

Hard rules:
  - Never say "free from", "allergen-free" or "safe". The strongest negative is
    "isn't listed" (enforced by a test).
  - Below the allergen confidence gate, nothing is interpreted (D-072).
  - Ambiguous sources (lecithin with no source named, "mixed nuts") are
    "uncertain", never "not listed".
"""

import json
import os
import re
from dataclasses import dataclass

DATA_DIR = os.environ.get("INSIDELABEL_DATA", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")))

# D-072: stricter than the 0.85 ingredient gate. Initial value, to be
# calibrated against gold files once allergen fields are in the eval set.
ALLERGEN_MIN_CONFIDENCE = 0.95

with open(os.path.join(DATA_DIR, "allergens.json"), encoding="utf-8") as _f:
    _TABLE = json.load(_f)

ALLERGENS = {a["code"]: a for a in _TABLE["allergens"]}
TRIGGERS = _TABLE["cross_contact_triggers"]
_NUT_WORDS = {"nuts", "mixed nuts", "nut paste"}
_SPECIFIC_NUTS = set(ALLERGENS["peanut"]["aliases"]) | set(ALLERGENS["tree_nuts"]["aliases"])

RANK = {"contains": 4, "may_contain": 3, "uncertain": 2, "not_listed": 1}


def _has(term, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def _strip_excluded(text, allergen):
    for ex in sorted(allergen.get("exclude", []), key=len, reverse=True):
        text = re.sub(r"(?<![a-z0-9])" + re.escape(ex) + r"(?![a-z0-9])", " ", text)
    return text


def _split_statement(statement):
    """Return (contains_parts, may_parts) from the printed allergen line."""
    contains, may = [], []
    for sentence in re.split(r"[.;\n]+", statement.lower()):
        s = sentence.strip()
        if not s:
            continue
        hits = [s.find(t) for t in TRIGGERS if t in s]
        if hits:
            i = min(hits)
            if s[:i].strip():
                contains.append(s[:i])
            may.append(s[i:])
        else:
            contains.append(s)
    return contains, may


@dataclass
class AllergenResult:
    code: str
    state: str
    evidence: str = ""
    statement_seen: bool = False

    def parent_text(self, who="your child"):
        # who="you" is the user's own profile (D-074): "your avoid list", not "you's".
        a = ALLERGENS[self.code]
        label, short = a["label"], a["short"]
        whose = "your" if who == "you" else f"{who}'s"
        if self.state == "contains":
            return f"Contains {short}. It's on {whose} avoid list."
        if self.state == "may_contain":
            return f"The pack says it may contain {short}."
        if self.state == "uncertain":
            then = "before you eat it" if who == "you" else f"before giving it to {who}"
            return (f"We can't tell whether \"{self.evidence}\" comes from {short}. "
                    f"Check with the brand {then}.")
        if self.state == "cannot_confirm":
            return (f"We couldn't read the label clearly enough to check for {short}. "
                    f"Please retake the ingredients photo.")
        text = f"{label[0].upper() + label[1:]} isn't listed in the ingredients"
        if self.statement_seen:
            text += " or the allergen line."
        else:
            text += ". We didn't see a \"may contain\" line in the photo, so check the pack."
        if not a.get("fssai_mandatory", True):
            text += f" Brands don't have to declare {short}, so this check is weaker."
        return text


def mentioned(text):
    """
    D-175: the allergens a text names anywhere, by their aliases and statement words
    (each allergen's `exclude` phrases first taken out: "coconut milk" is no milk).
    For the re-check's "nothing new" test only; never an allergen state.
    """
    low = (text or "").lower()
    out = set()
    for code, a in ALLERGENS.items():
        t = _strip_excluded(low, a)
        if any(_has(w, t) for w in a["aliases"] + a.get("statement_words", [])):
            out.add(code)
    return out


def check(ingredients, allergen_statement, codes, confidence=1.0, reliable=True):
    """Return {code: AllergenResult} for each avoid-list code."""
    unknown = [c for c in codes if c not in ALLERGENS]
    if unknown:
        raise ValueError(f"unknown allergen codes: {unknown}")

    if not reliable or not ingredients or confidence < ALLERGEN_MIN_CONFIDENCE:
        return {c: AllergenResult(c, "cannot_confirm") for c in codes}

    statement_seen = bool(allergen_statement and allergen_statement.strip())
    contains_parts, may_parts = _split_statement(allergen_statement) if statement_seen else ([], [])

    results = {}
    for code in codes:
        a = ALLERGENS[code]
        best = AllergenResult(code, "not_listed", statement_seen=statement_seen)

        def consider(state, evidence):
            nonlocal best
            if RANK[state] > RANK[best.state]:
                best = AllergenResult(code, state, evidence, statement_seen)

        # 1. Ingredient list.
        for tok in ingredients:
            low = _strip_excluded(tok.lower(), a)
            if any(_has(al, low) for al in a["aliases"]):
                consider("contains", tok)
                continue
            for amb in a.get("ambiguous", []):
                if not _has(amb, low):
                    continue
                if amb in _NUT_WORDS and any(_has(n, low) for n in _SPECIFIC_NUTS):
                    continue  # "cashew nuts" is specific, not ambiguous
                if any(_has(c, low) for c in a.get("ambiguous_cleared_by", [])):
                    continue  # "sunflower lecithin" names its source
                consider("uncertain", tok)

        # 2. Printed allergen line.
        words = a["statement_words"]
        for part in contains_parts:
            p = _strip_excluded(part, a)
            if any(_has(w, p) for w in words):
                consider("contains", part.strip())
            elif any(_has(w, p) for w in a.get("ambiguous", []) if w in _NUT_WORDS):
                consider("uncertain", part.strip())
        for part in may_parts:
            p = _strip_excluded(part, a)
            if any(_has(w, p) for w in words) or any(
                    _has(w, p) for w in a.get("ambiguous", []) if w in _NUT_WORDS):
                consider("may_contain", part.strip())

        results[code] = best
    return results

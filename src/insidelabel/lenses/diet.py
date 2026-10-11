#!/usr/bin/env python3
"""
diet.py - the two diet choices in a person's avoid list (D-198).

"Vegetarian only" and "No onion or garlic" (Sushil, 2026-10-11). They live in the
same `avoid` list as the allergen codes (profiles stay {ref, age, avoid}, D-074), but
they are checked here, from data/diet.json, and returned in /scan's `diet` block,
right after `allergens` (which stays first and unchanged, D-060).

Reads only what prompt.py already returns: the ingredient entries and
product.veg_mark ("veg", "non_veg", "not_visible"). No prompt change.

States follow allergens.py, strongest first: contains > uncertain > not_listed,
plus cannot_confirm (below 0.95 or a partial read, D-072). The brown mark is read
on the front, so it still counts on a partial list read.

Vegetarian follows FSSAI's definition (Labelling and Display Regulations 2020,
reg. 2(1)(o)): any part of an animal, birds, insects, fish, eggs or products of
animal origin; milk, milk products, honey, beeswax, carnauba wax and shellac are not
counted. Every INS number comes from core/tokenize.py (D-099).

Never a verdict, score or concern level (D-004), and never "pure veg", "veg-safe",
"Jain-friendly", "free from" or "safe" (D-042, D-071).
"""

import json
import os
import re
from dataclasses import dataclass, field

from insidelabel.core import tokenize as tok

DATA_DIR = os.environ.get("INSIDELABEL_DATA", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")))

with open(os.path.join(DATA_DIR, "diet.json"), encoding="utf-8") as _f:
    _TABLE = json.load(_f)

DIETS = {d["code"]: d for d in _TABLE["diets"]}
MIN_CONFIDENCE = 0.95                    # D-072: the allergen gate
RANK = {"contains": 3, "uncertain": 2, "not_listed": 1}
MARKS = ("veg", "non_veg", "not_visible")


def _has(term, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def _strip(text, words):
    for w in sorted(words, key=len, reverse=True):
        text = re.sub(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", " ", text)
    return text


def _upper(s):
    return s[0].upper() + s[1:] if s else s


@dataclass
class DietResult:
    code: str
    state: str
    evidence: str = ""                   # the entry as printed
    name: str = ""                       # what it is: "gelatin", "onion", "INS 471"
    comes_from: str = ""                 # its JECFA specification's source, "animal collagen (skin and bones)"
    can_be: str = ""                     # "plant or animal fat" (an uncertain INS)
    mark: str = None                     # the veg mark the result used, or None (no mark known)
    mark_from: str = None                # "photo" | "pack" | None
    complete: bool = True
    ins: str = None
    also_green: bool = False             # an animal item with the green mark printed too
    exempt: bool = False                 # reg. 5(4)(d): a product that carries no mark (honey, water, milk)
    sources: list = field(default_factory=list)


def _ins_rows(diet):
    return {r["ins"]: r for r in diet.get("ins", [])}


def _word_hit(diet, low):
    for w in diet.get("words", []):
        for a in sorted(w["aliases"], key=len, reverse=True):
            if _has(a, low):
                return w
    return None


def _flavour_only(diet, low):
    """'Chicken flavour': named after an animal food, made with or without it. The food, or None."""
    for u in diet.get("uncertain_words", []):
        if "with" in u and any(_has(a, low) for a in u["aliases"]):
            food = next((x for x in u["with"] if _has(x, low)), None)
            if food:
                return food
    return None


def _unnamed(diet, entry):
    """'Spices' with no breakdown in brackets (no_onion_garlic)."""
    base, groups = tok._peel(entry.lower())
    for u in diet.get("uncertain_words", []):
        if "with" in u:
            continue
        if any(_has(a, base) for a in u["aliases"]):
            return not (u.get("cleared_by_breakdown") and any(g.strip() for g in groups))
    return False


def _check_entries(diet, ingredients):
    best = DietResult(diet["code"], "not_listed")

    def consider(r):
        nonlocal best
        if RANK[r.state] > RANK[best.state]:
            best = r

    ins_rows = _ins_rows(diet)
    for entry in ingredients:
        low = _strip(entry.lower(), diet.get("exclude", []))
        # Every INS number through the one parser (D-099).
        for n in sorted(tok.ins_numbers(entry)):
            row = ins_rows.get(n)
            if not row:
                continue
            if row["state"] == "uncertain" and any(_has(c, low) for c in row.get("cleared_by", [])):
                continue
            consider(DietResult(diet["code"], row["state"], entry, row["name"], row.get("comes_from", ""),
                                row.get("can_be", ""), ins=n, sources=[row["source"]]))
        # Words. A flavour named after an animal food is uncertain, not contains.
        food = _flavour_only(diet, low)
        if food:
            consider(DietResult(diet["code"], "uncertain", entry, food, ins=None))
            continue
        w = _word_hit(diet, low)
        if w:
            consider(DietResult(diet["code"], "contains", entry, w["name"], w.get("comes_from", ""),
                                sources=[w["source"]] if w.get("source") else []))
            continue
        # Parts in brackets are entries of their own (tokenize.tokenize gives them too).
        if _unnamed(diet, entry):
            consider(DietResult(diet["code"], "uncertain", entry, "unnamed"))
    return best


def mark_exempt(product_name, ingredients):
    """
    Reg. 5(4)(d): mineral water, packaged drinking water, carbonated water, alcoholic beverages,
    liquid milk, milk powders and honey carry no veg mark, so a missing one is not a finding
    (advisor, 2026-10-11). True when the product name ends in one of the listed names, or every
    ingredient entry is one of the listed ingredients.
    """
    ex = DIETS["vegetarian"]["mark_exempt"]
    name = re.sub(r"[^a-z ]+", " ", (product_name or "").lower()).strip()
    name = re.sub(r"\s+", " ", name)
    if name and any(re.search(r"(?<![a-z])" + re.escape(n) + r"$", name) for n in ex["names"]):
        return True
    entries = [re.sub(r"\s+", " ", re.sub(r"\([^)]*\)|[^a-z ()]+", " ", e.lower())).strip()
               for e in (ingredients or [])]
    entries = [e for e in entries if e]
    return bool(entries) and all(e in ex["only_ingredients"] for e in entries)


def check(ingredients, codes, veg_mark=None, mark_from=None, confidence=1.0, reliable=True,
          complete=True, product_name=None):
    """
    Return {code: DietResult} for each diet code in `codes` (others are ignored).
    veg_mark: product.veg_mark, or None when no mark is known (a catalogue version
    stored without one). mark_from: "photo" or "pack". product_name: for reg. 5(4)(d).
    """
    out = {}
    exempt = mark_exempt(product_name, ingredients)
    mark = veg_mark if veg_mark in MARKS else None
    for code in [c for c in codes if c in DIETS]:
        diet = DIETS[code]
        sure = reliable and complete and bool(ingredients) and confidence >= MIN_CONFIDENCE
        if code == "vegetarian" and mark == "non_veg":
            # Reg. 5(4)(a): the pack's own declaration, read on the front.
            r = DietResult(code, "contains", name="brown mark")
            if sure:
                listed = _check_entries(diet, ingredients)
                if listed.state == "contains":
                    r.evidence, r.name, r.comes_from = listed.evidence, listed.name, listed.comes_from
                    r.name = "brown mark+" + listed.name
        elif not sure:
            r = DietResult(code, "cannot_confirm", complete=complete)
        else:
            r = _check_entries(diet, ingredients)
            if code == "vegetarian" and r.state == "contains" and mark == "veg":
                r.also_green = True
        r.mark = mark if code == "vegetarian" else None
        r.mark_from = mark_from if code == "vegetarian" else None
        r.exempt = exempt and code == "vegetarian"
        out[code] = r
    return out


# ------------------------------------------------------------------ words (used by screen.py)

def words(r, where="photo"):
    """
    D-198: (line, more) for one diet result, quoting the label. `line` is the card's short
    line (Sushil: card text stays short); `more` the fact under it, or None.
    """
    pack = "The pack we checked has" if where == "pack" else "The pack has"
    q = f"\"{r.evidence}\"" if r.evidence else ""
    if r.code == "vegetarian":
        if r.state == "contains" and r.name.startswith("brown mark"):
            listed = r.name.split("+", 1)[1] if "+" in r.name else None
            return (f"{pack} the brown non-vegetarian mark.",
                    f"{_upper(listed)} is listed: {q}." if listed else None)
        if r.state == "contains":
            more = []
            if r.ins:
                more.append(f"INS {r.ins} comes from {r.comes_from}.")
            elif r.name == "egg":
                more.append("FSSAI counts egg as non-vegetarian.")
            elif r.comes_from:
                more.append(f"It comes from {r.comes_from}.")
            if r.also_green:
                more.append(f"{pack.replace(' has', ' also has')} the green vegetarian mark.")
            return f"{_upper(r.name)} is listed: {q}.", " ".join(more) or None
        if r.state == "uncertain" and r.ins:
            line = f"INS {r.ins} can be made from {r.can_be}; the label doesn't say which."
            return line, (f"{pack} the green vegetarian mark." if r.mark == "veg" else None)
        if r.state == "uncertain":
            return f"We can't tell whether {q} is made from {r.name}; the label doesn't say.", None
        if r.state == "cannot_confirm":
            return ("Part of the list couldn't be read, so we can't check whether it's vegetarian. Check the pack."
                    if not r.complete else
                    "The list wasn't clear enough to check whether it's vegetarian. Check the pack."), None
        return None, None
    if r.state == "contains":
        return f"{_upper(r.name)} is listed: {q}.", None
    if r.state == "uncertain":
        return f"The list says {q} without naming what's in it, so we can't tell if it includes onion or garlic.", None
    if r.state == "cannot_confirm":
        return ("Part of the list couldn't be read, so we can't check for onion or garlic. Check the pack."
                if not r.complete else
                "The list wasn't clear enough to check for onion or garlic. Check the pack."), None
    return None, None


def green_quiet(r):
    """
    D-198 (Sushil, 2026-10-11): INS 471 or 322 with no source named, on a pack with the green
    mark, goes to "For you" as a quiet line; with no mark seen it stays an amber card.
    """
    return r.code == "vegetarian" and r.state == "uncertain" and bool(r.ins) and r.mark == "veg"


def cannot_confirm_both(complete):
    """Both diet choices unchecked: one line, not two (D-198)."""
    return ("Part of the list couldn't be read, so we can't check whether it's vegetarian or has onion or "
            "garlic. Check the pack." if not complete else
            "The list wasn't clear enough to check whether it's vegetarian or has onion or garlic. Check the pack.")


def text(r, where="photo"):
    """The whole of words(): /scan's `diet` block and Share carry it in one line."""
    line, more = words(r, where)
    return f"{line} {more}" if line and more else line


# D-198: said once in "For you" for a person on "Vegetarian only" when we had no mark to read.
NO_MARK = {
    "photo": "We didn't see the green or brown mark in the photos, so we checked the ingredient list only.",
    "pack": "We have no record of the veg mark on the pack we checked, so we checked the ingredient list only.",
}


def mark_note(r, where="photo"):
    """The quiet line for a vegetarian result with no mark to go on, or None."""
    if r.code != "vegetarian" or r.state == "contains" or r.mark in ("veg", "non_veg") or r.exempt:
        return None                      # reg. 5(4)(d): no mark expected on an exempt product
    return NO_MARK["pack" if where == "pack" else "photo"]

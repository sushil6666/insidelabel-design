"""
nutra.py - a health supplement's own checks (D-139, phase 2).

A supplement is judged by FSSAI's rules for supplements (the FSS (Nutra)
Regulations 2022 "as operationalised by FSSAI's direction of 18 October 2022",
D-139) and ICMR-NIN's nutrient requirements, not by the food checks: a tablet's
microcrystalline cellulose isn't an "industrial ingredient" of a food, and a
per-100-g threshold means nothing for a capsule.

What this module does, all rules over data/nutra_*.json (D-004):
- format():     tablets, capsules and syrups against food formats (gummies,
                powders, bars), from the pack's own words (5(1)(a), 6(1)(e)).
- statements(): the label statements of 5(12), found or not found; "not found"
                only on a complete read of both faces.
- usage():      a day's usage from the pack's usage statement ("1 tablet twice a day").
- amounts():    the composition table's amounts for one day beside ICMR-NIN's RDA for
                men and for women and its upper limit (Sushil 2026-09-30: the RDA is
                never called a limit). Every number must be in the second reading of
                the photo (as D-133); without one, no amount is shown.
- additives():  each additive against the list for that format; "not found" is never
                "not permitted" (the lists name excipients loosely, and the Drugs and
                Cosmetics Rules' colour list isn't read).
- plants():     Schedule II rows with a note, matched on the schedule's own names and
                the part the note belongs to.
The words a user reads are built in lenses/screen.py (D-091).
"""

import json
import os
import re

from insidelabel.core.tokenize import ins_numbers
from insidelabel.trace import DATA_DIR


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


RULES = _load("nutra_rules.json")
ADDITIVES = _load("nutra_additives.json")
PLANTS = _load("nutra_botanicals.json")
_ADDITIVE_ROWS = {r["ins"]: r for r in _load("additives.json")["additives"]}

_UNIT = {alias: unit for unit, aliases in RULES["units"].items() for alias in aliases}
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(mcg|µg|μg|ug|mg|g|gm|iu|i\.u\.)\b", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "half": 0.5, "a": 1, "an": 1}
_FREQ = (("thrice", 3), ("three times", 3), ("twice", 2), ("two times", 2), ("once", 1),
         ("daily", 1), ("a day", 1), ("per day", 1), ("every day", 1), ("each day", 1))
_UNITS = ("tablet", "capsule", "softgel", "gummy", "gummies", "scoop", "sachet", "serving", "pill", "strip",
          "teaspoon", "ml", "drop", "bar")
_PART_STOP = {"of", "the", "and", "whole", "parts", "part", "outer", "after", "boiling", "tender"}


def norm(text):
    t = (text or "").lower().replace("’", "'")
    return " " + " ".join(re.sub(r"[^a-z0-9.%'µμ]+", " ", t).split()) + " "


def _has(n, phrase):
    return f" {phrase.lower()} " in n


def _words_of(text):
    return [w for w in re.sub(r"\([^)]*\)", " ", text.lower()).replace("-", " ").split() if w.isalpha()]


def _unit_word(word):
    w = word.lower().rstrip("s")
    if w in ("gummie", "gummy"):
        return "gummy"
    return next((u for u in _UNITS if w == u.rstrip("s")), None)


# ---------------------------------------------------------------- format

def _pack_words(vision):
    product = vision.get("product") or {}
    words = [product.get("name"), product.get("variant"), (vision.get("composition") or {}).get("basis")]
    words += [s["text"] for s in vision.get("pack_statements") or []]
    return norm(" ".join(w for w in words if w))


def format_of(vision):
    """"tablet_capsule_syrup" (Annexure 3's list), "food" (13.6 and Appendix A), or None (unknown)."""
    n = _pack_words(vision)
    formats = ADDITIVES["formats"]
    if any(_has(n, w) for w in formats["tablet_capsule_syrup"]):
        return "tablet_capsule_syrup"
    if any(_has(n, w) for w in formats["food"]):
        return "food"
    return None


# ---------------------------------------------------------------- statements, 5(12)

def complete_read(vision):
    return (vision.get("front_status") == "read" and vision.get("back_status") == "read"
            and vision.get("ingredients_status") == "read")


def statements(vision, ocr_text=None):
    """[{id, text, found, printed}] for each 5(12) statement, or None when both faces weren't read whole."""
    if not complete_read(vision):
        return None
    printed = [(s["text"], s["face"]) for s in vision.get("pack_statements") or []]
    ocr = norm(ocr_text or "")
    out = []
    for row in RULES["statements"]:
        hit = None
        for text, face in printed:
            if row["face"] == "front" and face != "front":
                continue
            if any(_has(norm(text), m) for m in row["match"]):
                hit = text
                break
        if hit is None and row["face"] != "front" and any(_has(ocr, m) for m in row["match"]):
            hit = next(m for m in row["match"] if _has(ocr, m))
        out.append({"id": row["id"], "text": row["text"], "found": hit is not None, "printed": hit,
                    "basis": row["fssai_basis"]})
    return out


# ---------------------------------------------------------------- a day's usage

_COUNT = re.compile(r"\b(\d+(?:\.\d+)?|one|two|three|four|half|a|an)(?:\s*(?:-|to|or)\s*(\d+|one|two|three|four))?"
                    r"\s+([a-z]+)")


def _num(word):
    return float(_WORDNUM[word]) if word in _WORDNUM else float(word)


def usage(vision):
    """{"count": 2.0, "unit": "tablet", "text": "Take 1 tablet twice a day"} from the pack's own usage line, or None.
    A range ("1-2 capsules") counts its upper end: the most the pack says to take in a day."""
    for s in vision.get("pack_statements") or []:
        t = s["text"].lower()
        for m in _COUNT.finditer(t):
            unit = _unit_word(m.group(3))
            if not unit:
                continue
            count = _num(m.group(2)) if m.group(2) else _num(m.group(1))
            rest = t[m.end():]
            times = re.search(r"(\d+)\s*times\s*(?:a|per|in a)\s*day", rest)
            freq = int(times.group(1)) if times else next((f for w, f in _FREQ if w in rest), None)
            if freq:
                return {"count": count * freq, "unit": unit, "text": s["text"]}
    return None


def basis(vision):
    """{"count": 1.0, "unit": "tablet"} from "Each tablet contains", "Per 2 capsules", or None."""
    text = ((vision.get("composition") or {}).get("basis") or "").lower()
    m = re.search(r"(?:each|per|every)\s+(\d+(?:\.\d+)?\s+)?(?:film[- ]coated\s+|hard\s+|soft\s+|chewable\s+)?([a-z]+)", text)
    if not m:
        return None
    unit = _unit_word(m.group(2))
    return {"count": float(m.group(1) or 1), "unit": unit} if unit else None


# ---------------------------------------------------------------- amounts beside ICMR-NIN

def _nutrient_of(name):
    """(rda row, kept) for a composition line; kept False when the amount is of a salt, not the nutrient."""
    n = norm(name)
    for row in RULES["rda"]:
        if any(_has(n, alias) for alias in row["names"]):
            salt = any(re.search(rf"\b{w}", n) for w in RULES["salt_words"])
            says_nutrient = any(w in n for w in RULES["salt_amount_of_nutrient"])
            return row, (not salt) or says_nutrient
    return None, False


def _amount(text):
    m = _AMOUNT.search(text or "")
    if not m:
        return None
    unit = _UNIT.get(m.group(2).lower())
    return {"value": float(m.group(1)), "unit": unit, "printed": m.group(0)} if unit else None


def _in_text(number, text):
    """The number, digit for digit, in the second reading (as lenses/nutrition.py does)."""
    digits = number.rstrip("0").rstrip(".") if "." in number else number
    return re.search(rf"(?<![\d.]){re.escape(digits)}(?:\.0+)?(?![\d.])", text or "") is not None


def amounts(vision, ocr_text):
    """
    {"state": ..., "per": {"count", "unit"}, "daily": usage or None, "rows": [...]}.
    state: "shown", "not_read" (no composition), "unverified" (no second reading).
    Each row: nutrient, label, value (per day, or per unit when no usage), unit, printed,
    rda_men, rda_women, tul, over_tul, note.
    """
    comp = vision.get("composition") or {}
    if comp.get("status") not in ("read", "partial") or not comp.get("rows"):
        return {"state": "not_read", "rows": []}
    if not (ocr_text or "").strip():
        return {"state": "unverified", "rows": []}
    per, day = basis(vision), usage(vision)
    factor, daily = 1.0, None
    if per and day and per["unit"] == day["unit"]:
        factor, daily = day["count"] / per["count"], day
    rows = []
    for line in comp["rows"]:
        row, kept = _nutrient_of(line["name"])
        amount = _amount(line.get("amount"))
        if not (row and kept and amount) or amount["unit"] != row["unit"]:
            continue
        number = re.search(r"\d+(?:\.\d+)?", amount["printed"]).group(0)
        if not _in_text(number, ocr_text):
            continue                                  # D-133: a number the second reading doesn't have isn't shown
        value = amount["value"] * factor
        rows.append({"nutrient": row["nutrient"], "label": row["label"], "unit": row["unit"], "value": value,
                     "printed": amount["printed"], "line": line["name"], "rda_men": row["rda_men"],
                     "rda_women": row["rda_women"], "tul": row["tul_adult"], "table": row["table"],
                     "over_tul": bool(daily and row["tul_adult"] is not None and value > row["tul_adult"]),
                     "note": row.get("note")})
    return {"state": "shown", "per": per, "daily": daily, "rows": rows}


# ---------------------------------------------------------------- additives

_GROUP_WORDS = {"ASCORBYL ESTERS": ["ascorbyl"], "BENZOATES": ["benzoate", "benzoic"], "CAROTENOIDS": ["carotene", "carotenoid"],
                "CHLOROPHYLLS AND CHLOROPHYLLINS, COPPER COMPLEXES": ["chlorophyll", "chlorophyllin"],
                "ETHYLENE DIAMINE TETRA ACETATES": ["edta", "ethylene diamine"], "IRON OXIDES": ["iron oxide"],
                "PHOSPHATES": ["phosphate"], "POLYSORBATES": ["polysorbate"], "RIBOFLAVINS": ["riboflavin"],
                "SACCHARINS": ["saccharin"], "SORBATES": ["sorbate", "sorbic"]}


def _name_in(entry_n, name):
    words = norm(re.sub(r"\([^)]*\)", " ", name)).strip()
    return bool(words) and f" {words} " in entry_n


def _tab_row(names, rows):
    for r in rows:
        if any(_name_in(x, r["name"]) or any(f" {a} " in x for a in r.get("aliases", [])) for x in names):
            return r
    return None


def additives(ingredients, fmt):
    """
    [{entry, ins, name, listed, where, gmp}] for each entry that is an additive: an INS number
    (core/tokenize.py, D-099), a name on the supplement lists, or (tablets, capsules and syrups
    only) a name on Annexure 3's tablet list. Listed: on the list for its format, on the 10 May
    2022 order's list, or in Appendix A's GMP table (5(4)(a)). `listed` None: can't be checked
    (a colour in a tablet: the list points to the Drugs and Cosmetics Rules, not read).
    """
    tab = ADDITIVES["tablet_capsule_syrup"]["rows"]
    hs = ADDITIVES["supplements_13_6"]["rows"]
    extra = ADDITIVES["order_10_may_2022"]["rows"]
    tablets = fmt == "tablet_capsule_syrup"
    out = []
    for entry in ingredients or []:
        n = norm(entry)
        for ins in ins_numbers(entry) or [None]:
            row = _ADDITIVE_ROWS.get(ins) if ins else None
            name = (row or {}).get("name")
            names = [n] + ([norm(name)] if name else [])
            in_tab = _tab_row(names, tab)
            in_hs = next((r for r in hs if (ins and r["ins"] == ins) or any(_name_in(x, r["name"]) for x in names)
                          or any(w in x for w in _GROUP_WORDS.get(r["name"], []) for x in names)), None)
            in_extra = next((r for r in extra if any(_name_in(x, r["name"]) for x in names)), None)
            gmp = bool(row and "GMP table" in (row.get("fssai_basis") or ""))
            if not (ins or in_hs or in_extra or (tablets and in_tab)):
                continue                              # not an additive we can recognise in this format
            colour = bool(row and row.get("class") == "colour") or "colour" in n or "color" in n
            if tablets:
                listed = bool(in_tab or in_extra or gmp) or (None if colour else False)
            else:
                listed = bool(in_hs or in_extra or gmp)
            out.append({"entry": entry, "ins": ins, "name": name or (in_tab or in_hs or in_extra or {}).get("name"),
                        "listed": listed, "where": "tablet_capsule_syrup" if tablets else "supplements_13_6", "gmp": gmp})
    return out


# ---------------------------------------------------------------- plants, Schedule II

def _part_named(entry_n, row):
    if len(row["parts_in_schedule"]) == 1:
        return True
    for alt in re.sub(r"\([^)]*\)", " ", row["part"]).split("/"):
        words = [w for w in _words_of(alt) if w not in _PART_STOP]
        if words and all(f" {w}" in entry_n for w in words):
            return True
    return False


def plants(ingredients, vision=None):
    """[{row, entry}] for each noted Schedule II row a list entry (or composition line) names, with its part."""
    entries = list(ingredients or []) + [r["name"] for r in ((vision or {}).get("composition") or {}).get("rows") or []]
    hits, seen = [], set()
    for entry in entries:
        n = norm(entry)
        for row in PLANTS["rows"]:
            if row["id"] in seen:
                continue
            latin = any(_has(n, " ".join(b.split()[:2])) for b in row["botanical"])
            named = latin or any(_has(n, name) for name in row["names"])
            if named and _part_named(n, row):
                seen.add(row["id"])
                hits.append({"row": row, "entry": entry})
    return hits


# ---------------------------------------------------------------- protein powder

def protein_powder(vision, fmt):
    product = vision.get("product") or {}
    words = norm(" ".join(filter(None, [product.get("name"), product.get("variant")]
                                 + list((vision.get("ingredients") or [])[:1]))))
    return fmt == "food" and _has(words, "protein") and any(
        _has(_pack_words(vision), w) for w in ("powder", "scoop", "scoops"))

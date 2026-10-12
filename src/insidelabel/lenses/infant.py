"""
infant.py - an infant food's own checks (D-140, phase 3), in shadow.

A food for infant nutrition is judged by FSSAI's rules for it (the FSS (Foods for
Infant Nutrition) Regulations 2020), not by the food checks: the regulation defines
each product type and what its label must and must not say. Every rule is a row of
data/infant_rules.json, read from the compendium's page images (D-046); the model
only copies the printed words (D-004).

In shadow (D-140, Sushil 2026-09-30): /scan computes this and stores it with the
scan's reading for reviewers (/review). D-200 (Sushil 2026-10-12, "Everything"): with
INSIDELABEL_INFANT_TO_USERS on (the default) users see it too, in lenses/screen.py's words
and in Compare (lenses/side_by_side.py); off, only the allergen lines, the kind and the list.

What this module does:
- product_type(): infant formula, follow-up formula, milk cereal or processed cereal
                  based complementary food, traditional food, from the product's
                  printed name and the front's own words, never from regulation 4's
                  statements (they name "infant milk substitute or infant food").
- statements():   regulation 4's statements found or not found; "not found" only on a
                  complete read of both faces, and only those for the type's chapter.
- no_milk():      4(3): "Contains no milk or milk products or milk derivatives", found or not
                  found, only where the allergen check says milk is not listed.
- words():        4(2)'s words the label shall not exhibit, where printed.
- free_from():    5(1): preservatives and colours (by the additive's class) and flavours.
- hydrogenated(): hydrogenated fat, for the types whose section says so.
- composition():  part 4, reviewers only: a number the pack prints per 100 g, seen by the
                  second reading too, beside the type's range (data/infant_composition.json,
                  with FSSAI's 18 October 2022 revisions). Facts side by side.
- additives():    5(2): an INS number on the list that the type's additive list (and
                  Schedule I(d)'s carriers, data/infant_additives.json) doesn't name,
                  "not found in the list", never "not permitted".
Pictures (4(2)) are a reviewer's check (reviewer_checks), never the app's.
"""

import json
import os
import re

from insidelabel.core.pack_kind import _has, norm
from insidelabel.lenses import allergens, nutrition
from insidelabel.core.tokenize import ins_numbers
from insidelabel.lenses.nutra import complete_read
from insidelabel.trace import DATA_DIR


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


RULES = _load("infant_rules.json")
ADDITIVES = _load("infant_additives.json")
COMPOSITION = _load("infant_composition.json")
_TYPES = {t["id"]: t for t in RULES["types"]}
_CLASS = {r["ins"]: r["class"] for r in _load("additives.json")["additives"]}
_HYDRO = next(r for r in _load("ingredient_notes.json")["rows"] if r["id"] == "hydrogenated_fat")


def _mandatory(text_n):
    """One of regulation 4's statements, which name "infant milk substitute or infant food" whatever the type."""
    return _has(text_n, "infant milk substitute or infant food") or any(
        _has(text_n, m) for row in RULES["statements"] for m in row["match"])


def product_type(vision):
    """
    {"id", "chapter", "printed", "basis"} from the product's printed name (the name, the
    front's own words, front statements other than regulation 4's), or None: a reviewer sets it.
    """
    product = vision.get("product") or {}
    names = [product.get("name"), product.get("variant"), (vision.get("front_identity") or {}).get("name")]
    names += list(vision.get("front_claims") or [])
    names += [s["text"] for s in vision.get("pack_statements") or []
              if s.get("face") == "front" and not _mandatory(norm(s["text"]))]
    for row in RULES["types"]:                    # the table's order: most specific names first
        for text in filter(None, names):
            if any(_has(norm(text), p) for p in row["phrases"]):
                return {"id": row["id"], "chapter": row["chapter"], "printed": text, "basis": row["basis"]}
    return None


def statements(vision, ocr_text=None, ptype=None):
    """
    [{id, text, found, printed, basis}] for regulation 4's statements, or None when both
    faces weren't read whole. Without a product type, the chapter-specific ones are left out.
    """
    if not complete_read(vision):
        return None
    printed = [(s["text"], s.get("face")) for s in vision.get("pack_statements") or []]
    ocr = norm(ocr_text or "")
    out = []
    for row in RULES["statements"]:
        if ptype is None and len(row["chapters"]) < 2:
            continue
        if ptype is not None and ptype["chapter"] not in row["chapters"]:
            continue
        hit = next((text for text, face in printed
                    if (row["face"] != "front" or face == "front") and any(_has(norm(text), m) for m in row["match"])),
                   None)
        if hit is None and row["face"] != "front" and any(_has(ocr, m) for m in row["match"]):
            hit = next(m for m in row["match"] if _has(ocr, m))
        out.append({"id": row["id"], "text": row["text"], "found": hit is not None, "printed": hit,
                    "basis": row["fssai_basis"]})
    return out


def no_milk(vision, ocr_text=None):
    """
    4(3): {text, found, printed, basis} for a pack whose list shows no milk, or None: when both
    faces weren't read whole, or the allergen check (D-072's confidence gate) doesn't say milk
    is not listed (contains, may contain and uncertain say nothing).
    """
    if not complete_read(vision):
        return None
    confidence = (vision.get("confidence") or {}).get("ingredients", 0.0)
    milk = allergens.check(vision.get("ingredients") or [], vision.get("allergen_statement"), ["milk"],
                           confidence=confidence)["milk"]
    if milk.state != "not_listed":
        return None
    row = RULES["no_milk"]
    texts = [s["text"] for s in vision.get("pack_statements") or []] + [vision.get("allergen_statement")]
    hit = next((t for t in filter(None, texts) if any(_has(norm(t), m) for m in row["match"])), None)
    if hit is None and any(_has(norm(ocr_text or ""), m) for m in row["match"]):
        hit = next(m for m in row["match"] if _has(norm(ocr_text), m))
    return {"text": row["text"], "found": hit is not None, "printed": hit, "basis": row["fssai_basis"]}


def words(vision, ocr_text=None):
    """[{word, printed}] for each of 4(2)'s words found on the label (statements, name, claims, OCR text)."""
    product = vision.get("product") or {}
    texts = [s["text"] for s in vision.get("pack_statements") or []]
    texts += [product.get("name"), product.get("variant")] + list(vision.get("front_claims") or [])
    texts += [ocr_text]
    out = []
    for w in RULES["words_not_to_use"]["words"]:
        hit = next((t for t in filter(None, texts) if _has(norm(t), w)), None)
        if hit is not None:
            out.append({"word": w, "printed": hit if hit is not ocr_text else None})
    return out


def free_from(ingredients):
    """[{entry, why}] for each ingredient that is a preservative, a colour or a flavour (5(1))."""
    rule = RULES["free_from"]
    out = []
    for entry in ingredients or []:
        n = norm(entry)
        classes = sorted({_CLASS.get(i) for i in ins_numbers(entry)} & set(rule["classes"]))
        flavour = (any(_has(n, w) for w in rule["flavour_words"])
                   and not any(_has(n, w) for w in rule["not_flavour"]))
        why = classes + (["flavour"] if flavour else [])
        if why:
            out.append({"entry": entry, "why": why})
    return out


def hydrogenated(ingredients, ptype):
    """[{entry, text, basis}] for hydrogenated fat on the list, for the types whose section rules it out."""
    row = next((r for r in RULES["no_hydrogenated"]["rows"] if ptype and r["type"] == ptype["id"]), None)
    if row is None:
        return []
    names = [x for x in _HYDRO["names"] if not row.get("partial_only") or x.startswith("partially hydrogenated")]
    out = []
    for entry in ingredients or []:
        n = norm(entry)
        if any(_has(n, norm(x).strip()) for x in _HYDRO["exclude"]):
            continue
        if any(_has(n, norm(x).strip()) for x in names):
            out.append({"entry": entry, "text": row["text"], "basis": row["fssai_basis"]})
    return out


def _key(ins):
    """An INS number compared on its number and any letter suffix, not roman sub-numbers: the
    parser keeps a lone 'i' ("500i") but drops 'ii' ("500ii" reads 500)."""
    digits = "".join(c for c in ins if c.isdigit())
    suffix = ins[len(digits):] if ins.startswith(digits) else ""
    return digits if set(suffix) <= set("iv") else digits + suffix


def _keys(rows):
    out = set()
    for r in rows:
        if r["ins"]:
            out |= {_key(i) for i in ins_numbers(f"INS {r['ins']}")} | set(r.get("also") or [])
    return out


def type_additives(type_id):
    """(basis, the INS keys the type's list and Schedule I(d) name), or (None, None) for no list."""
    t = ADDITIVES["types"].get(type_id)
    if t is None:
        return None, None
    rows = ADDITIVES["types"][t["same_as"]]["rows"] if t.get("same_as") else t["rows"]
    return t["basis"], _keys(rows) | _keys(ADDITIVES["carriers"]["rows"])


def additives(ingredients, ptype):
    """
    5(2): {"basis", "not_found": [{entry, ins}]} for the INS numbers on the list that the type's
    additive list (and Schedule I(d)) don't name, or None without a type. Never "not permitted":
    carry-over additives are allowed (5(2)) and the type may be misread. Entries under vitamins or
    minerals are nutrient sources (Schedule I), not additives: left out.
    """
    if ptype is None:
        return None
    basis, keys = type_additives(ptype["id"])
    if keys is None:
        return None
    out = []
    for entry in ingredients or []:
        n = norm(entry)
        if any(_has(n, w) for w in ("vitamin", "vitamins", "mineral", "minerals")):
            continue
        for ins in sorted(ins_numbers(entry)):
            if _key(ins) not in keys:
                out.append({"entry": entry, "ins": ins})
    return {"basis": basis, "not_found": out}


# ---------------------------------------------------------------- composition (reviewers only)

_MACROS = {"protein": "protein", "total_fat": "total_fat", "carbohydrate": "carbohydrate", "sodium": "sodium"}
_SCALE = {("g", "mg"): 1000.0, ("mg", "g"): 0.001, ("mg", "mcg"): 1000.0, ("mcg", "mg"): 0.001,
          ("g", "mcg"): 1e6, ("mcg", "g"): 1e-6}


def _nutrient_of(label):
    """The composition table's nutrient a printed row names, or None. A ratio is never a nutrient."""
    n = norm(label)
    if _has(n, "ratio"):
        return None
    key = nutrition.nutrient_key(label)
    if key in _MACROS:
        return _MACROS[key]
    for nutrient, names in COMPOSITION["names"].items():
        if any(_has(n, name) for name in names):
            return nutrient
    return None


def _cell(cell, label, unit_col):
    """(value, unit, printed) for a printed per 100 g cell; the unit from the cell, the unit column or the label."""
    text = ("" if cell is None else str(cell)).strip()
    m = re.search(r"(?<![\d.])" + nutrition._NUM, text)
    if not m or nutrition._LT.search(text):
        return None
    unit = nutrition._unit_of(text[m.end():], unit_col, label)
    return nutrition._f(m.group(1)), unit, m.group(1)


def composition(vision, ocr_text, ptype):
    """
    Part 4, reviewers only: [{nutrient, label, printed, unit, value, range, where, basis}] for each
    nutrient the pack prints per 100 g whose number the second reading of the photo (ocr_text) also
    shows, beside the type's range (data/infant_composition.json). None without a type, a table
    per 100 g or a second reading. `where` is "within", "below" or "above": facts, never "fails".
    """
    table = COMPOSITION["types"].get(ptype["id"]) if ptype else None
    raw = vision.get("nutrition")
    if table is None or not isinstance(raw, dict) or not (ocr_text or "").strip():
        return None
    if nutrition.form_of(raw.get("per_100_basis")) != "solid":
        return None
    seen = nutrition.ocr_numbers(ocr_text)
    rows = {r["nutrient"]: r for r in table["rows"]}
    out, done = [], set()
    for r in raw.get("rows") or []:
        if not isinstance(r, dict):
            continue
        nutrient = _nutrient_of(r.get("nutrient"))
        if nutrient not in rows or nutrient in done:
            continue
        got = _cell(r.get("per_100"), r.get("nutrient"), r.get("unit"))
        if got is None:
            continue
        value, unit, printed = got
        row = rows[nutrient]
        if unit is None or (unit != row["unit"] and (unit, row["unit"]) not in _SCALE):
            continue                                  # IU, kJ, or no unit: not compared
        if nutrition._f(printed) not in seen:
            continue                                  # not in the second reading: not shown (D-133)
        done.add(nutrient)
        v = value if unit == row["unit"] else value * _SCALE[(unit, row["unit"])]
        lo, hi = row["per_100_g"]
        where = "below" if lo is not None and v < lo else "above" if hi is not None and v > hi else "within"
        out.append({"nutrient": nutrient, "label": r.get("nutrient"), "printed": printed, "unit": unit,
                    "value": round(v, 4), "range": [lo, hi], "range_unit": row["unit"], "where": where,
                    "optional": bool(row.get("optional")), "basis": row["fssai_basis"]})
    return out


def check(vision, ingredients=None, ocr_text=None):
    """Every infant check for one reading, as stored with the scan for reviewers (D-140, in shadow)."""
    ingredients = vision.get("ingredients") if ingredients is None else ingredients
    ptype = product_type(vision)
    return {
        "version": RULES["_meta"]["version"],
        "type": ptype,
        "complete_read": complete_read(vision),
        "statements": statements(vision, ocr_text, ptype),
        "no_milk": no_milk(vision, ocr_text),
        "words": words(vision, ocr_text),
        "free_from": free_from(ingredients),
        "hydrogenated": hydrogenated(ingredients, ptype),
        "additives": additives(ingredients, ptype),
        "composition": composition(vision, ocr_text, ptype),
        "reviewer_checks": RULES["reviewer_checks"],
    }

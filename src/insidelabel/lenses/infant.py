"""
infant.py - an infant food's own checks (D-140, phase 3), in shadow.

A food for infant nutrition is judged by FSSAI's rules for it (the FSS (Foods for
Infant Nutrition) Regulations 2020), not by the food checks: the regulation defines
each product type and what its label must and must not say. Every rule is a row of
data/infant_rules.json, read from the compendium's page images (D-046); the model
only copies the printed words (D-004).

In shadow (D-140, Sushil 2026-09-30): /scan computes this and stores it with the
scan's reading for reviewers (/review); users see the allergen lines, the kind and
the ingredient list only, until a lawyer has read the IMS Act questions.

What this module does:
- product_type(): infant formula, follow-up formula, milk cereal or processed cereal
                  based complementary food, traditional food, from the product's
                  printed name and the front's own words, never from regulation 4's
                  statements (they name "infant milk substitute or infant food").
- statements():   regulation 4's statements found or not found; "not found" only on a
                  complete read of both faces, and only those for the type's chapter.
- words():        4(2)'s words the label shall not exhibit, where printed.
- free_from():    5(1): preservatives and colours (by the additive's class) and flavours.
- hydrogenated(): hydrogenated fat, for the types whose section says so.
Pictures (4(2)) are a reviewer's check (reviewer_checks), never the app's.
"""

import json
import os

from insidelabel.core.pack_kind import _has, norm
from insidelabel.core.tokenize import ins_numbers
from insidelabel.lenses.nutra import complete_read
from insidelabel.trace import DATA_DIR


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


RULES = _load("infant_rules.json")
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


def check(vision, ingredients=None, ocr_text=None):
    """Every infant check for one reading, as stored with the scan for reviewers (D-140, in shadow)."""
    ingredients = vision.get("ingredients") if ingredients is None else ingredients
    ptype = product_type(vision)
    return {
        "version": RULES["_meta"]["version"],
        "type": ptype,
        "complete_read": complete_read(vision),
        "statements": statements(vision, ocr_text, ptype),
        "words": words(vision, ocr_text),
        "free_from": free_from(ingredients),
        "hydrogenated": hydrogenated(ingredients, ptype),
        "reviewer_checks": RULES["reviewer_checks"],
    }

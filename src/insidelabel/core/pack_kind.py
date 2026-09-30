"""
pack_kind.py - what kind of pack this is: food, supplement, infant, special_medical
or not_food (D-139, D-140).

Why a rule and not the model: the kind decides which checks run and what the
result may say, so it is a judgement, and judgements are rules over data (D-004).
The model only copies what is printed (prompt rule 11: `pack_statements`,
`licences`); `data/pack_kinds.json` names the words, each from the regulation that
asks packs to print them, with its page (D-046).

Order (data/pack_kinds.json _meta):
1. Licence (D-116, extended by D-139). A non-FSSAI licence printed and no FSSAI
   licence on a complete read of both faces: `not_food` (FSS Act 3(1)(j) leaves out
   "drugs and medicinal products"). An FSSAI licence decides "food" whatever else
   is printed. The shape of the product never decides.
2. Medical words: `special_medical` (including preterm, hypoallergenic and other
   special medical infant foods).
3. Infant words: `infant`.
4. Supplement words: `supplement`.
5. The catalogue's category (13.x), for a pack whose printed words say nothing.
6. Otherwise `food`, exactly as before D-139.
A printed kind and a chosen category that disagree are sent to a reviewer
(`review`), never resolved here.
"""

import json
import os
import re

from insidelabel.trace import DATA_DIR
with open(os.path.join(DATA_DIR, "pack_kinds.json"), encoding="utf-8") as _fh:
    TABLE = json.load(_fh)

KINDS = tuple(TABLE["kinds"])
PARTS = {k: tuple(v["parts"]) for k, v in TABLE["kinds"].items()}
# D-140: result fields the server never sends for a kind in shadow; kinds /compare accepts.
WITHHOLD = {k: tuple(v.get("withhold", ())) for k, v in TABLE["kinds"].items()}
WITHHOLD_KEYS = {k: v.get("withhold_keys", {}) for k, v in TABLE["kinds"].items()}
WITHHOLD_REASON = {k: v.get("withhold_reason") for k, v in TABLE["kinds"].items()}
COMPARABLE = frozenset(TABLE["comparable"])
_LIC = TABLE["licences"]
_FSSAI_NUMBER = re.compile(r"(?<!\d)\d{%d}(?!\d)" % _LIC["fssai_number_digits"])
_ORDER = ("special_medical", "infant", "supplement")


def norm(text):
    """Lower case, apostrophes gone ("MOTHER'S" = "mothers"), anything else not a letter or digit a space."""
    t = (text or "").lower().replace("’", "").replace("'", "").replace("`", "")
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", t).split()) + " "


def _has(text_n, phrase):
    return f" {phrase} " in text_n


def _printed(vision):
    """Every statement the kind may be read from, as [(text, face, where)]. Never the
    ingredient list or the manufacturer (a "... Nutraceuticals Pvt Ltd" isn't a kind)."""
    out = [(s["text"], s["face"], "statement") for s in vision.get("pack_statements") or []]
    product = vision.get("product") or {}
    for key in ("name", "variant"):
        if product.get(key):
            out.append((product[key], None, f"product.{key}"))
    out += [(c, "front", "front_claim") for c in vision.get("front_claims") or []]
    return [x for x in out if not any(_has(norm(x[0]), w) for w in TABLE["company_words"]["phrases"])]


def licences(vision):
    """({fssai: [...], other: [...]}) licence lines as printed. back_identity's FSSAI number counts too."""
    fssai, other = [], []
    lines = list(vision.get("licences") or [])
    number = ((vision.get("back_identity") or {}).get("fssai_licence") or "").strip()
    if number:
        lines.append({"text": number, "face": "back", "from": "back_identity"})
    for line in lines:
        n = norm(line["text"])
        if any(_has(n, w) for w in _LIC["fssai_words"]) or _FSSAI_NUMBER.search(line["text"].replace(" ", "")):
            fssai.append(line)
        elif any(_has(n, w) for w in _LIC["licence_words"]):
            other.append(line)
    return {"fssai": fssai, "other": other}


def category_kind(code):
    """The kind a catalogue category implies, or None (an ordinary food category)."""
    cats = TABLE["catalogue_categories"]
    for prefix in sorted(cats, key=len, reverse=True):
        if code and (code == prefix or code.startswith(prefix + ".")):
            return cats[prefix]
    return None


def decide(vision, category=None):
    """
    vision: the reading (after gemini.harden). category: the catalogue's FSSAI
    category code for this pack, if any. Returns {code, evidence[], licences,
    category, review[]}; `review` lists why a person should look.
    """
    vision = vision or {}
    evidence, review = [], []
    lic = licences(vision)
    both_read = vision.get("front_status") == "read" and vision.get("back_status") == "read"

    code = None
    if lic["other"] and not lic["fssai"]:
        ev = {"rule": "licence", "text": lic["other"][0]["text"], "face": lic["other"][0].get("face")}
        if both_read:
            code = "not_food"
            evidence.append(ev)
        else:
            # D-139: a partial read never gives not_food; the licence may be on the face not read.
            review.append("a non-FSSAI licence is printed and no FSSAI licence was read, "
                          "but not both faces were read (D-116: look at the whole pack)")

    if code is None:
        printed = [(norm(t), t, face, where) for t, face, where in _printed(vision)]
        found = {}
        for row in TABLE["words"]:
            for phrase in row["phrases"]:
                hit = next(((t, face, where) for n, t, face, where in printed if _has(n, phrase)), None)
                if hit:
                    found.setdefault(row["kind"], []).append(
                        {"rule": row["id"], "text": hit[0], "face": hit[1], "where": hit[2]})
                    break
        for kind in _ORDER:
            if kind in found:
                code = kind
                evidence += found[kind]
                break
        for row in TABLE["supporting"]:
            hit = next(((t, face) for n, t, face, _w in printed if any(_has(n, p) for p in row["phrases"])), None)
            if hit:
                evidence.append({"rule": row["id"], "text": hit[0], "face": hit[1], "supporting": True})

    implied = category_kind(category)
    if code is None and implied:
        code = implied
        evidence.append({"rule": "catalogue_category", "text": category, "face": None})
    elif category and (code or "food") != (implied or "food"):
        review.append(f"the pack reads as {code or 'food'} but its category {category} is "
                      f"{implied or 'an ordinary food category'}")
    code = code or "food"
    return {"code": code, "evidence": evidence, "licences": lic, "category": category, "review": review}


def parts(code):
    return PARTS.get(code, PARTS["food"])

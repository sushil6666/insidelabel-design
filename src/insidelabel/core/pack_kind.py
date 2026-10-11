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
   D-187 (item #82): only words that name a non-food licence ("Drug Lic", "Mfg Lic",
   "DL No", "Ayurvedic" or "AYUSH" beside a licence) make a licence non-FSSAI; food
   packs print their FSSAI licence as a plain "Lic. No." all the time. A line with
   a 10 to 13 digit number starting 1 or 2 is a probable FSSAI licence whose end
   wasn't read: never not_food, a reviewer checks the pack. And not_food needs no
   ordinary food signal (a nutrition table, an ordinary food category): with one,
   a reviewer looks instead.
   D-190 (item #85): "Ayurvedic medicine", "Ayurvedic proprietary medicine" or "AYUSH
   medicine" printed anywhere the kind is read from (or on a licence line) is the same
   non-food sign without a licence line, and loses to the same things: an FSSAI or
   probable FSSAI licence, an ordinary food signal, a partial read. D-195: except a
   nutrition table, which Ayurvedic packs print too (a Baidyanath Chyawanprash, 2026-10-11).
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
_PROBABLE = _LIC["probable_fssai_number"]
_PROBABLE_NUMBER = re.compile(r"(?<!\d)[%s]\d{%d,%d}(?!\d)" % (
    "".join(_PROBABLE["first_digit"]), _PROBABLE["min_digits"] - 1, _PROBABLE["max_digits"] - 1))
_MEDICINE = _LIC["medicine_words"]
_MEDICINE_LABEL = _LIC["medicine_label_words"]["phrases"]
PROBABLE_NOTE = "probable FSSAI licence, last digits not read: check the pack"
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


def _non_food(n):
    """D-187: a line naming a non-food licence; a plain "Lic No." names none."""
    if any(_has(n, w) for w in _LIC["non_food_licence_words"]):
        return True
    return any(_has(n, w) for w in _MEDICINE["phrases"]) and any(_has(n, w) for w in _MEDICINE["next_to"])


def medicine_printed(vision):
    """D-190: the first line printing "Ayurvedic medicine" (or a listed phrase), as
    {rule, text, face, where}, or None. "Ayurvedic" alone, "Ayurvedic recipe" say nothing."""
    lines = [(t, face, where) for t, face, where in _printed(vision)]
    lines += [(l["text"], l.get("face"), "licence") for l in vision.get("licences") or []]
    for text, face, where in lines:
        n = norm(text)
        if any(_has(n, p) for p in _MEDICINE_LABEL):
            return {"rule": "medicine_printed", "text": text, "face": face, "where": where}
    return None


def licences(vision):
    """({fssai: [...], probable: [...], other: [...]}) licence lines as printed. back_identity's
    FSSAI number counts too. `probable`: a number that looks like an FSSAI licence with its end
    not read (D-187)."""
    fssai, probable, other = [], [], []
    lines = list(vision.get("licences") or [])
    number = ((vision.get("back_identity") or {}).get("fssai_licence") or "").strip()
    if number:
        lines.append({"text": number, "face": "back", "from": "back_identity"})
    for line in lines:
        n = norm(line["text"])
        if any(_has(n, w) for w in _LIC["fssai_words"]) or _FSSAI_NUMBER.search(line["text"].replace(" ", "")):
            fssai.append(line)
        elif _PROBABLE_NUMBER.search(line["text"].replace(" ", "")):
            probable.append(line)
        elif _non_food(n):
            other.append(line)
    return {"fssai": fssai, "probable": probable, "other": other}


def food_signals(vision, category=None, table=True):
    """D-187: what says ordinary food whatever the licence lines say: a nutrition table
    printed, an ordinary food category. D-195: `table=False` leaves the table out, for a
    pack that prints "Ayurvedic medicine" itself (Ayurvedic packs print nutrition values too)."""
    out = []
    if table and ((vision.get("nutrition") or {}).get("status")) in TABLE["food_signals"]["nutrition_status"]:
        out.append("a nutrition table")
    if category and category_kind(category) is None:
        out.append(f"category {category}, an ordinary food category")
    return out


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
    if lic["probable"] and not lic["fssai"]:
        review.append(f'{PROBABLE_NOTE} ("{lic["probable"][0]["text"]}")')
    sign = ev = None
    if not lic["fssai"] and not lic["probable"]:
        if lic["other"]:
            ev = {"rule": "licence", "text": lic["other"][0]["text"], "face": lic["other"][0].get("face")}
            sign = "a non-FSSAI licence is printed"
        else:
            # D-190: "Ayurvedic medicine" printed is the same sign without a licence line.
            ev = medicine_printed(vision)
            sign = ev and f'"{ev["text"]}" is printed'
    if sign:
        # D-195 (Baidyanath Chyawanprash, 2026-10-11): a nutrition table doesn't overrule the
        # pack's own "Ayurvedic medicine"; D-187's table guard stays for licence lines, where a
        # misread "Lic No." was the risk. An ordinary food category still does.
        signals = food_signals(vision, category, table=ev.get("rule") != "medicine_printed")
        if both_read and signals:
            # D-187: the licence rule alone never overrules an ordinary food signal.
            review.append(f"{sign} and no FSSAI licence was read, but the pack "
                          f"shows {' and '.join(signals)} (D-116: look at the whole pack)")
        elif both_read:
            code = "not_food"
            evidence.append(ev)
        else:
            # D-139: a partial read never gives not_food; the licence may be on the face not read.
            review.append(f"{sign} and no FSSAI licence was read, "
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

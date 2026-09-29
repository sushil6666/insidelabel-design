"""
The review checker (D-117): the second agent, and deliberately not a model.

Gemini drafts a catalogue record; this confirms it only when every check
passes, using rules and the one independent reader we already have: the text
Google Cloud Vision read from the same back photo (stored on the scan, D-094).
A second call to the same model would repeat its blind spots; Cloud Vision
doesn't share them. Anything that fails goes to a person, with the reasons.

Each check is written against a mistake seen on the first supermarket run
(2026-09-27): compound ingredients split at a bracket, a garbled line that
dropped words (Bisk Farm TOP GOLD), an Ayurvedic-medicine pack (D-116), a
"Sugar Free" claim, a category that is a judgement call.
"""

import difflib
import json
import os
import re
import unicodedata

from insidelabel import barcode as barcode_rules
from insidelabel.lenses import nutrition
from insidelabel.trace import DATA_DIR

IN_SCOPE_KINDS = ("new_product", "reformulation")

_RULES = json.load(open(os.path.join(DATA_DIR, "category_words.json"), encoding="utf-8"))["rules"]
_NORM = json.load(open(os.path.join(DATA_DIR, "normalization.json"), encoding="utf-8"))
_SUGARS = sorted({s.lower() for s in _NORM["sugar_aliases"]["added_sugar"]} | {"sugar"}, key=len, reverse=True)
_CLAIM_RULES = json.load(open(os.path.join(DATA_DIR, "claim_rules.json"), encoding="utf-8"))["rules"]

# "PEANUT BASED SPREAD (Proprietary Food - 4.2.2.5 Spread)": the pack's own category.
# The pack's own category: "PROPRIETARY FOOD (CATEGORY 7.2.2)", or the code first, as on
# beverage mixes: "DAIRY BASED BEVERAGE MIX (1.1.2) PROPRIETARY FOOD" (items 27 and 28).
_DECLARED = re.compile(r"proprietary\s+food\s*[-:(\u2013]?\s*(\d{1,2}(?:\.\d{1,2}){1,4})"
                       r"|\((\d{1,2}(?:\.\d{1,2}){1,4})\)\s*proprietary\s+food", re.I)
_CODE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,4})\b")
# D-116: an AYUSH drug licence. Its *absence* of an FSSAI number is never used.
_AYUSH = re.compile(r"\b(ayurvedic|siddha|unani)\s+(proprietary\s+)?medicine", re.I)
_WORD = re.compile(r"[a-z]{3,}")
_BRACKETS = {"(": ")", "[": "]", "{": "}"}

# Where an ingredient list ends on Indian packs, and the words around it that
# aren't ingredients. Tuned on the first shadow run (2026-09-27, items 12 to 16):
# a recipe printed near the list, a nutrition panel Cloud Vision reads in among
# it, "Net Weight" after it.
_SECTION_END = ("nutrition", "allergen", "storage", "store in", "manufactured", "mfd", "marketed",
                "mkt", "best before", "net qty", "net quantity", "net weight", "net wt", "serving size",
                "for complaints", "consumer care", "customer care")
_NOT_INGREDIENTS = {"ingredients", "ingredient", "contains", "contain", "and", "the", "with", "numbers",
                    "brackets", "are", "per", "international", "numbering", "system", "each", "approx"}
# Nutrition-panel words. Cloud Vision can read a curved panel into the middle of
# the list, often cut short ("energ", "satur"), so a prefix counts too.
# "Added" (sugars) and "sodium" are panel rows too (item 13); a dropped "sodium
# bicarbonate" is still caught by its second word.
_NUTRITION = ("energy", "kcal", "saturated", "serving", "servings", "recommended", "carbohydrate",
              "carbohydrates", "total", "trans", "nutrition", "nutritional", "dietary", "cholesterol",
              "added", "sodium")


def _fold(text):
    """Lower case without accents: CRÈME and creme are the same word."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", (text or "").lower())
                   if not unicodedata.combining(ch))


def _words(text):
    return _WORD.findall(_fold(text))


def _nutrition_word(w):
    return len(w) >= 4 and any(n.startswith(w) or w.startswith(n) for n in _NUTRITION)


def _found(word, pool):
    """In the pool exactly, or close enough for OCR noise ('refinedwheat' is not close to 'refined')."""
    return word in pool or bool(difflib.get_close_matches(word, pool, n=1, cutoff=0.8))


def _balanced(line):
    stack = []
    for ch in line:
        if ch in _BRACKETS:
            stack.append(_BRACKETS[ch])
        elif ch in _BRACKETS.values():
            if not stack or stack.pop() != ch:
                return False
    return not stack


def _base(line):
    """An ingredient line without its brackets: 'Sugar (25%)' -> 'sugar'."""
    return re.sub(r"[\(\[\{].*", "", line).strip().lower()


def _is_sugar(line):
    b = _base(line)
    return any(b == s or b.startswith(s + " ") for s in _SUGARS)


def declared_category(ocr_text):
    m = _DECLARED.search(ocr_text or "")
    return (m.group(1) or m.group(2)) if m else None


def category_code(text):
    """The code alone: the drafter sometimes returns "14.1.5 Coffee, coffee substitutes, ..." (item 24)."""
    m = _CODE.match(text or "")
    return m.group(1) if m else (text or "").strip()


def rule_category(name, variant, ingredients, ocr_text):
    """The category the word table gives, or None when no rule, or rules that disagree, apply."""
    title = _fold(f"{name or ''} {variant or ''}")
    label = _fold(ocr_text)
    codes = set()
    for r in _RULES:
        if "name_any" in r and not any(p in title for p in r["name_any"]):
            continue
        if "label_any" in r and not any(p in label for p in r["label_any"]):
            continue
        if any(p in title for p in r.get("name_none", [])):
            continue
        if "sugar_in_first" in r and not any(_is_sugar(x) for x in ingredients[:r["sugar_in_first"]]):
            continue
        if r.get("no_added_sugar") and any(_is_sugar(x) for x in ingredients):
            continue
        if "first_ingredient_any" in r and not (ingredients and any(
                _base(ingredients[0]).startswith(p) for p in r["first_ingredient_any"])):
            continue
        codes.add(r["code"])
    return codes.pop() if len(codes) == 1 else None


def _ingredient_section(ocr_text, ingredients):
    """
    The part of Cloud Vision's text that holds the ingredient list, or "".

    Starts at the "ingredients" heading nearest before the draft's first
    ingredient (a recipe on the pack can say "ingredients" too). Ends where the
    draft's last ingredient ends, plus the rest of that sentence (up to 80
    characters), so words the draft dropped from the end of the list still show;
    and never past a heading like "Nutrition" or "Net Weight".
    """
    low = _fold(ocr_text)
    starts = [m.start() for m in re.finditer("ingredient", low)]
    if not starts:
        return ""
    first = (_words(ingredients[0]) or [""])[0] if ingredients else ""

    def gap(s):
        i = low.find(first, s) if first else -1
        return i - s if i >= 0 else len(low)

    start = min(starts, key=gap)
    stop = min([i for i in (low.find(t, start + 10) for t in _SECTION_END) if i > 0] or [len(low)])
    last = (_words(ingredients[-1]) or [""])[-1] if ingredients else ""
    j = low.rfind(last, start, stop) if last else -1
    if j < 0:
        return low[start:stop]
    end = j + len(last)
    tail = re.search(r"(?<!\d)\.(?!\d)|\n\s*\n", low[end:end + 80])
    return low[start:min(stop, end + (tail.start() if tail else 80))]


def independent_read(ingredients, ocr_text, allergen_statement=None):
    """
    Does Cloud Vision's text of the back photo confirm this ingredient list?
    Returns (section_found, missing, lost): whether the text holds an
    ingredient list at all; the list's words Cloud Vision never saw; and the
    words of Cloud Vision's list the given list doesn't have. Confirmed when
    section_found and both lists are empty. Used by the review checker (D-117)
    and by /scan, to ask for a clearer photo of a new pack (D-118).
    """
    pool = sorted(set(_words(ocr_text)))
    missing = sorted({w for w in _words(" ".join(ingredients)) if pool and not _found(w, pool)})
    covered = sorted(set(_words(" ".join(list(ingredients) + [allergen_statement or ""]))))
    section = _ingredient_section(ocr_text, ingredients)
    lost = sorted({w for w in _words(section)
                   if w not in _NOT_INGREDIENTS and not _nutrition_word(w) and not _found(w, covered)})
    return bool(section), (missing if pool else ["(no text)"]), lost


def independent_read_confirmed(ingredients, ocr_text, allergen_statement=None):
    found, missing, lost = independent_read(ingredients, ocr_text, allergen_statement)
    return found and not missing and not lost


def _claim_rule_hits(claims):
    hits = []
    for c in claims or []:
        low = c.lower()
        for r in _CLAIM_RULES:
            if any(p in low for p in r.get("match", [])):
                hits.append(f'"{c}" ({r["id"]})')
    return hits


def check(draft, ctx):
    """
    draft: the drafter's answer (see draft_prompt.DRAFT_SCHEMA).
    ctx:   kind, ocr_text (Cloud Vision, back photo), raw (the scan's reading),
           request (the scan's options), categories (set of codes), has_front.
    Returns [{check, ok, detail}], every check, in order.
    """
    out = []

    def add(name, ok, detail=""):
        out.append({"check": name, "ok": bool(ok), "detail": detail})

    ingredients = [x.strip() for x in draft.get("ingredients") or [] if x and x.strip()]
    claims = [x.strip() for x in draft.get("front_claims") or [] if x and x.strip()]
    ocr = ctx.get("ocr_text") or ""
    raw = ctx.get("raw") or {}
    code = category_code(draft.get("category"))

    add("in_scope", ctx.get("kind") in IN_SCOPE_KINDS,
        f"{ctx.get('kind')} items stay with people for now" if ctx.get("kind") not in IN_SCOPE_KINDS else "")
    add("draft_complete", bool(ingredients and code and (draft.get("name") or "").strip()),
        "" if ingredients and code else "the draft has no ingredients or no category")
    add("independent_text", bool(ocr.strip()),
        "" if ocr.strip() else "no Cloud Vision text on the scan: nothing independent to check against")

    # Ingredients against the independent reader, both ways (shared with /scan, D-118).
    pool = sorted(set(_words(ocr)))
    section, missing, lost = independent_read(ingredients, ocr, draft.get("allergen_statement"))
    missing = missing if pool else []
    add("ingredients_in_ocr", pool and not missing,
        f"not in Cloud Vision's text: {', '.join(missing[:12])}" if missing else "")
    unbalanced = [x for x in ingredients if not _balanced(x)]
    add("brackets_balance", not unbalanced,
        f"unbalanced: {'; '.join(unbalanced[:3])}" if unbalanced else "")
    add("nothing_lost", section and not lost,
        "no ingredient list found in Cloud Vision's text" if not section else
        (f"in Cloud Vision's ingredient list but not in the draft: {', '.join(lost[:12])}" if lost else ""))

    # D-133: every number of the nutrition table the version would publish is in
    # Cloud Vision's text of the back photo; otherwise a person looks.
    lost_numbers = nutrition.not_in_text(ctx.get("nutrition"), ocr)
    add("nutrition_in_ocr", not lost_numbers,
        f"nutrition numbers not in Cloud Vision's text: {', '.join(lost_numbers[:8])}" if lost_numbers else "")

    statement = draft.get("allergen_statement") or ""
    stray = [w for w in _words(statement) if pool and not _found(w, pool)]
    add("allergen_line_in_ocr", not stray, f"not in Cloud Vision's text: {', '.join(stray[:8])}" if stray else "")

    # Category: the pack's own, or the word table's; never the drafter's alone.
    declared = declared_category(ocr)
    table = rule_category(draft.get("name"), draft.get("variant"), ingredients, ocr)
    if code and code not in (ctx.get("categories") or set()):
        add("category", False, f"{code} is not an FSSAI category code")
    elif declared:
        add("category", code == declared, f"the pack declares {declared}" + ("" if code == declared else f", draft says {code}"))
    elif table:
        add("category", code == table, f"the word table gives {table}" + ("" if code == table else f", draft says {code}"))
    else:
        add("category", False, "the pack declares no category and no word-table rule applies: a person chooses")

    # The pack and the reading.
    bc = (draft.get("barcode") or (ctx.get("request") or {}).get("barcode") or "").strip()
    reason = barcode_rules.check(bc)[1] if bc else "missing"
    add("barcode", reason is None, "" if reason is None else f"barcode {bc or '(none)'}: {reason}")
    conf = ((raw.get("confidence") or {}).get("ingredients") or 0)
    complete = raw.get("ingredients_status") == "read"
    add("reading_gate", conf >= 0.95 and complete,
        "" if conf >= 0.95 and complete else f"reading confidence {conf}, ingredients {raw.get('ingredients_status')}")
    match = (raw.get("product_match") or {}).get("status")
    # D-035: two photos can't prove one pack; the user's "Both photos are of the same pack"
    # is the mechanism, so it settles an indeterminate match (never a mismatch).
    attested = bool((ctx.get("request") or {}).get("pairing_confirmed"))
    same = match != "mismatch" and not (ctx.get("has_front") and claims and match != "match" and not attested)
    add("same_pack", same, "" if same else f"front and back not confirmed as one pack ({match})")
    sources = (ctx.get("request") or {}).get("photo_sources") or {}
    uploaded = [k for k, v in sources.items() if v == "upload"]
    add("camera_photos", not uploaded, f"uploaded, not taken: {', '.join(uploaded)} (D-106)" if uploaded else "")

    # What always needs a person.
    ayush = bool(draft.get("ayush_licence_seen")) or bool(_AYUSH.search(ocr))
    add("no_ayush_licence", not ayush, "an AYUSH medicine licence is on the pack (D-116)" if ayush else "")
    hits = _claim_rule_hits(claims)
    add("no_rule_claims", not hits, f"front claims a claim rule covers: {'; '.join(hits)} (D-051)" if hits else "")
    doubts = [d for d in draft.get("doubts") or [] if d and d.strip()]
    add("no_doubts", not doubts, f"the drafter's doubts: {'; '.join(doubts[:4])}" if doubts else "")
    return out


def outcome(checks):
    return "confirmed" if checks and all(c["ok"] for c in checks) else "needs_person"

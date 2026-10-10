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
from insidelabel.core import pack_kind
from insidelabel.core.tokenize import ins_numbers
from insidelabel.lenses import allergens as allergen_checker
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
# D-157 (refines D-118): a date or batch stamp printed across the ingredient panel
# ("AUG/26-APR", report #5) is not an ingredient the draft lost. Months always (as
# whole words only: "marjoram" and "mayonnaise" stay); the stamp words of Indian packs.
# "B.No" has no word of three letters, so it never reaches LOST anyway.
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec")
_STAMP_WORDS = {"mfd", "mfg", "exp", "best", "before", "batch", "lot"}
# A word in a stamp: next to a digit or "/" ("26-apr", "aug/"), or alone on its line.
_STAMPED = re.compile(r"(?<=[\d/-])[a-z]{3,5}(?![a-z])|(?<![a-z])[a-z]{3,5}(?=[\d/-])"
                      r"|^[ \t]*[a-z]{3,5}[ \t]*$", re.M)
# The heading Cloud Vision reads twice where the parts of a back overlap ("ING" + "DIENT'S").
_HEADINGS = ("ingredient", "ingredients")
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


# D-158: words that are never a cut word, wherever they sit. Every word of an allergen
# alias and of an allergen's statement words (allergens.json: "egg", "wheat", and "nut"
# from "pine nut"), since allergens come first (D-060); and the one-word names in
# normalization.json's synonyms ("salt", "msg", "vanaspati"), which the engine reads
# as ingredients. A dropped one of these next to a longer word still refuses.
_ALLERGEN_ROWS = json.load(open(os.path.join(DATA_DIR, "allergens.json"), encoding="utf-8"))["allergens"]
_NEVER_CUT = ({w for r in _ALLERGEN_ROWS for a in r["aliases"] + r.get("statement_words", []) for w in _words(a)}
              | {n for k, v in _NORM["synonyms"].items() for n in [k, *v] if re.fullmatch(r"[a-z]{3,}", n)})


def _line_ends(text):
    """The first and last word of each line: where an overlap or the photo's edge cuts a word (D-158)."""
    out = set()
    for line in text.splitlines():
        ws = _words(line)
        if ws:
            out.update((ws[0], ws[-1]))
    return out


def _nutrition_word(w):
    return len(w) >= 4 and any(n.startswith(w) or w.startswith(n) for n in _NUTRITION)


def _stamp_words(section):
    """
    The words of a date or batch stamp in this text (D-157). A month or stamp word
    counts wherever it is; a close misread of a month ("augt") only inside a stamp,
    next to a digit or "/" or alone on its line, so a real ingredient that looks a
    little like a month in running text is never dropped.
    """
    out = {w for w in _words(section) if w in _MONTHS or w in _STAMP_WORDS}
    for m in _STAMPED.finditer(section):
        w = m.group(0).strip()
        if difflib.get_close_matches(w, _MONTHS, n=1, cutoff=0.8):
            out.add(w)
    return out


def _cut(word, covered, ends):
    """
    A word cut short where Cloud Vision read an overlap of the back's parts, or the
    edge of the photo (D-157): the start of a word the list has ("frac", "leci"), or a
    piece of the "ingredients" heading ("ing", "dient"). A cut word that starts no
    word of the list still counts as lost.
    D-158: only at the start or end of a line (`ends`), where a cut happens, and never
    an allergen or an ingredient name: "Nutmeg, Nut," mid-line, or "Egg" at a line's
    end beside "Eggless", is a dropped ingredient, not a cut one.
    """
    if word not in ends or word in _NEVER_CUT:
        return False
    if any(c != word and c.startswith(word) for c in covered):
        return True
    return any(h != word and (h.startswith(word) or h.endswith(word)) for h in _HEADINGS)


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
    return _section_bounds(ocr_text, ingredients)[0]


def _section_bounds(ocr_text, ingredients, end_words=1):
    """
    The part of Cloud Vision's text that holds the ingredient list, or "".

    Starts at the "ingredients" heading nearest before the draft's first
    ingredient (a recipe on the pack can say "ingredients" too). Ends where the
    draft's last ingredient ends, plus the rest of that sentence (up to 80
    characters), so words the draft dropped from the end of the list still show;
    and never past a heading like "Nutrition" or "Net Weight".
    Returns (section, ended): ended is False when the draft's last word isn't in
    the section, so where the list ends wasn't found (D-175).
    end_words: D-175's re-check ends at the latest of the last entry's final words (3), as
    a misread last word can also sit earlier in the list ("(FROM SOYBEAN)" in the chocolate
    chips, "(FROM SOYABEAN)" at the end). The D-117 and D-118 checks keep 1.
    """
    low = _fold(ocr_text)
    starts = [m.start() for m in re.finditer("ingredient", low)]
    if not starts:
        return "", False
    first = (_words(ingredients[0]) or [""])[0] if ingredients else ""

    def gap(s):
        i = low.find(first, s) if first else -1
        return i - s if i >= 0 else len(low)

    start = min(starts, key=gap)
    stop = min([i for i in (low.find(t, start + 10) for t in _SECTION_END) if i > 0] or [len(low)])
    end = -1
    for last in (_words(ingredients[-1])[-end_words:] if ingredients else []):
        j = low.rfind(last, start, stop)
        if j >= 0:
            end = max(end, j + len(last))
    if end < 0:
        return low[start:stop], False
    tail = re.search(r"(?<!\d)\.(?!\d)|\n\s*\n", low[end:end + 80])
    return low[start:min(stop, end + (tail.start() if tail else 80))], True


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
    stamps = _stamp_words(section)
    ends = _line_ends(section)
    lost = sorted({w for w in _words(section)
                   if w not in _NOT_INGREDIENTS and w not in stamps and not _nutrition_word(w)
                   and not _found(w, covered) and not _cut(w, covered, ends)})
    return bool(section), (missing if pool else ["(no text)"]), lost


def independent_read_confirmed(ingredients, ocr_text, allergen_statement=None):
    found, missing, lost = independent_read(ingredients, ocr_text, allergen_statement)
    return found and not missing and not lost


def glued_seen(missing, ingredients, ocr_text):
    """
    D-191: the MISSING words Cloud Vision did read, glued to their neighbour: Gemini's
    "Ground Nut Oil" printed or read as "groundnut" leaves "nut" missing although the
    text has it (8901058022223, 2026-10). A word counts as seen when it and the word
    before or after it in the same entry, joined, are in the text (the same fuzzy match
    as MISSING). Used only by /scan's ask (D-118); the D-117 checker stays strict.
    """
    pool = sorted(set(_words(ocr_text)))
    seen = set()
    for entry in ingredients or []:
        ws = _words(entry)
        for i, w in enumerate(ws):
            if w in missing and any(_found(g, pool) for g in
                                    ([ws[i - 1] + w] if i else []) + ([w + ws[i + 1]] if i + 1 < len(ws) else [])):
                seen.add(w)
    return sorted(seen)


def lost_ins_numbers(ingredients, ocr_text):
    """
    D-160: the INS numbers in Cloud Vision's ingredient list (the section
    independent_read() reads) that the given list doesn't have. LOST holds words
    only, so "Preservative (211)" dropped by Gemini shows there as "preservative";
    this gives /scan's gate the 211. Read with core/tokenize.ins_numbers (D-099).
    Not part of independent_read(): the D-117 checker stays as it is.
    """
    section = _ingredient_section(ocr_text, ingredients)
    return sorted(ins_numbers(section) - ins_numbers(list(ingredients or [])))


# D-175: the heading a printed list starts with, up to its colon when there is one.
_HEADING = re.compile(r"^\W*ingredi\w*\s*(?:\([^)]*\))?\s*[:\-]?", re.I)


def _pieces(text):
    """
    D-175 (refined 2026-10-08, after the server's 57 packs): a list cut at every comma,
    brackets or not. The same cut is made on the stored list joined, so like is compared
    with like: a stored list that splits a compound entry ("PLAIN CHOCOLATE CHIPS (6.2%)
    {SUGAR", "COCOA SOLIDS", ...) and a text whose bracket Cloud Vision dropped ("(500(ii),
    503 (ii), STARCH") count the same as the printed list. A new entry is still one more
    piece ("Sugar" beside "Invert sugar").
    """
    body = _HEADING.sub("", text, count=1)
    return [e for e in (x.strip().rstrip(".").strip() for x in body.split(",")) if e]


def unchanged(ingredients, allergen_statement, ocr_text):
    """
    D-175: is this photo's text clearly the published list again? Used by /scan to skip
    the paid read of a re-check photo; it never becomes a fact, a verdict or a finding
    (D-004, D-034), and a "not clear" only means the normal read runs.

    "unchanged" only when all of these hold on the photo's text (Cloud Vision, or
    Tesseract when Vision is off, D-093):
      - the list is there, and where it ends was found (the stored list's last word);
      - nothing missing: every word of every stored entry is in the text
        (independent_read's MISSING, with its fuzzy match for OCR noise);
      - nothing new: no word of the text's list that the stored list and allergen
        statement lack (independent_read's LOST, with D-157 and D-158's stamp, panel
        and cut words left out);
      - no new INS number (lost_ins_numbers, core/tokenize, D-099);
      - no new allergen: no allergen word anywhere in the text (the "Contains" line
        too) whose allergen the stored list and statement don't name;
      - the same number of entries (the advisor, 2026-10-08): the text's list and the
        stored list, each cut at every comma (_pieces), have as many pieces, so "Sugar"
        added beside "Invert sugar" counts;
      - the same order: piece i of the text holds the words of stored piece i, because
        the order feeds the sugar chip ("2nd of 11").
    Returns {decision, ...} with what each check found, for the scan's trace (D-092).
    """
    ingredients = [x for x in ingredients or [] if x and x.strip()]
    text = ocr_text or ""
    section, ended = _section_bounds(text, ingredients)
    found, missing, lost = independent_read(ingredients, text, allergen_statement)
    lost_ins = lost_ins_numbers(ingredients, text) if section else []
    stored = allergen_checker.mentioned(" , ".join(ingredients + [allergen_statement or ""]))
    new_allergens = sorted(allergen_checker.mentioned(text) - stored)
    counted, _ended = _section_bounds(text, ingredients, end_words=3)
    entries = _pieces(counted) if section else []
    wanted = _pieces(_fold(", ".join(ingredients)))
    out_of_order = []
    if len(entries) == len(wanted):
        for want, got in zip(wanted, entries):
            pool = sorted(set(_words(got)))
            if not all(_found(w, pool) for w in _words(want)):
                out_of_order.append(want)
    same = (found and ended and not missing and not lost and not lost_ins and not new_allergens
            and len(entries) == len(wanted) and not out_of_order)
    return {"decision": "unchanged" if same else "not_clear", "section_found": bool(found),
            "list_end_found": ended, "missing": missing, "lost": lost, "lost_ins": lost_ins,
            "new_allergens": new_allergens, "entries": len(entries), "stored_entries": len(wanted),
            "out_of_order": out_of_order}


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
    # D-143: a code only the camera scanner read goes to a person, who reads the printed digits.
    unsure = barcode_rules.unconfirmed(ctx.get("barcode_check"))
    add("barcode_confirmed", not unsure, barcode_rules.check_text(unsure) if unsure else "")
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

    # D-139, D-140: the kind the pack's printed words give, against the chosen category.
    # Anything but ordinary food goes to a person: its own checks aren't built yet.
    kind = pack_kind.decide(raw, category=code)
    add("pack_kind", kind["code"] == "food" and not kind["review"],
        "" if kind["code"] == "food" and not kind["review"] else
        "; ".join([f"the pack reads as {kind['code']}"] * (kind["code"] != "food") + kind["review"]))

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

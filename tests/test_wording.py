"""
Wording lint (D-042, D-071). Enforced here so nobody has to remember it.

Two layers:
  1. Consumer-facing fields in data/*.json. `_meta`, `note` and match lists
     are internal and not checked.
  2. Real output from every consumer surface, run on invented labels that
     contain none of the forbidden words. Any hit therefore comes from our
     own templates, not from text quoted off a pack.
"""
import base64
import json
import os
import re

from fastapi.testclient import TestClient

from insidelabel.api.main import app
from insidelabel.lenses.allergens import ALLERGENS, AllergenResult
from insidelabel.lenses.compare import Product, compare, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# D-042: never about the brand, never a legal or safety conclusion.
FORBIDDEN = [
    "misleading", "false", "falsely", "illegal", "non-compliant", "noncompliant",
    "violation", "violates", "violating", "lying", "lie", "lies", "toxic",
    "dangerous", "poison", "poisonous", "fraud", "cheat", "cheating",
]
# D-071 / D-063: the strongest negative is "isn't listed"; nothing implies safety.
FORBIDDEN_SAFETY = ["safe", "safely", "free from", "allergen-free", "allergen free", "healthy",
                    # D-198: the diet choices quote the label; they never certify a pack.
                    "pure veg", "veg-safe", "veg safe", "jain-friendly", "jain friendly", "100% veg",
                    "suitable for vegetarians", "suitable for vegetarian"]

_PATTERN = re.compile(
    r"(?<![a-z0-9-])(" + "|".join(re.escape(w) for w in FORBIDDEN + FORBIDDEN_SAFETY) + r")(?![a-z0-9-])",
    re.IGNORECASE,
)

# table -> consumer-facing string fields
CONSUMER_FIELDS = {
    "additives.json": ("additives", ["name", "why"]),
    "nova_markers.json": ("markers", ["name"]),
    "allergens.json": ("allergens", ["label", "short"]),
    "diet.json": ("diets", ["label", "short"]),
    "claim_rules.json": ("rules", ["label"]),
}


# D-200 (Sushil, 2026-10-12): never about an infant pack, in our words. "best" is allowed only
# inside regulation 4(1)(a)'s notice, exactly as the pack printed it.
# D-201 (Sushil, 2026-10-13): "inside/outside FSSAI's range" are facts; these never are.
INFANT_FORBIDDEN = ["safe", "best", "recommended", "healthy", "suitable for your baby",
                    "high", "too much", "fails", "not allowed", "violation"]
INFANT_NOTICE = "MOTHER'S MILK IS BEST FOR YOUR BABY"
_INFANT = re.compile(r"(?<![a-z0-9-])(" + "|".join(re.escape(w) for w in INFANT_FORBIDDEN) + r")(?![a-z0-9-])",
                     re.IGNORECASE)


def infant_hits(obj, printed=()):
    """The infant words in every string of obj, after taking out the notice where the pack printed it
    word for word (a string that is the printed notice, or the notice inside quotes)."""
    notices = [p for p in printed if p == INFANT_NOTICE]
    out = []
    for text in strings(obj) if not isinstance(obj, str) else [obj]:
        if text in notices:
            continue
        for n in notices:
            text = text.replace(f'"{n}"', "").replace(f"\u201c{n}\u201d", "")
        out += [m.group(0) for m in _INFANT.finditer(text)]
    return out


def hits(text):
    return [m.group(0) for m in _PATTERN.finditer(text or "")]


def strings(obj, skip_keys=frozenset()):
    """Every string value in a JSON-like object. Keys are field names, not copy."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip_keys:
                yield from strings(v, skip_keys)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v, skip_keys)
    elif isinstance(obj, str):
        yield obj


def assert_clean(texts, where):
    bad = [(t, hits(t)) for t in texts if hits(t)]
    assert not bad, f"{where}: forbidden wording\n" + "\n".join(f"  {h} in: {t!r}" for t, h in bad)


# ---------------------------------------------------------------- 1. tables

def test_lint_catches_what_it_should():
    assert hits("This label is misleading.") == ["misleading"]
    assert hits("Milk-free and SAFE") == ["SAFE"]
    assert hits("safety data sheet") == []          # word boundary
    assert hits("non-compliant") == ["non-compliant"]


def test_content_tables():
    for fname, (section, fields) in CONSUMER_FIELDS.items():
        with open(os.path.join(ROOT, "data", fname), encoding="utf-8") as f:
            rows = json.load(f)[section]
        texts = [r[k] for r in rows for k in fields if isinstance(r.get(k), str)]
        assert texts, f"{fname}: no consumer fields found - CONSUMER_FIELDS is stale"
        assert_clean(texts, fname)


# ---------------------------------------------------------------- 2. output

c = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

LABELS = [
    "Refined wheat flour (Maida), Sugar, Invert syrup, Palm oil, Colour (INS 102, INS 110), "
    "Emulsifiers (INS 322, INS 471), Preservative (INS 211), Sweetener (INS 955), Maltodextrin, "
    "Flavour enhancer (INS 621), Added flavours (Artificial vanilla)",
    "Roasted peanuts, Salt",
    "Carbonated water, Sugar, Acidity regulator (330), Caffeine",
]
CLAIMS = ["No added sugar", "No preservatives", "Made with real mango", "Sugar free"]


def test_analyze_and_claim_check_output():
    for raw in LABELS:
        j = c.post("/claim-check", json={"raw_ingredients": raw, "front_claims": CLAIMS}).json()
        # verdict.flags carry `matched_as` / `token` copied from the label; the
        # labels above are clean, so everything is checked.
        assert_clean(list(strings(j)), f"/claim-check {raw[:30]!r}")


# One profile per age band, each avoiding everything, so every screen line is produced.
PROFILES = [{"ref": "me", "age": "adult", "avoid": list(ALLERGENS)},
            {"ref": "p1", "age": "toddler", "avoid": list(ALLERGENS)},
            {"ref": "p2", "age": "kid", "avoid": []}]


def test_scan_disclosures_and_allergen_text():
    for status in ("read", "partial"):
        vision = {
            "front_status": "read", "back_status": "read", "ingredients_status": status,
            "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
            "product_match": {"status": "indeterminate", "evidence": []},
            "front_identity": None,
            "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
            "ingredient_lines": [LABELS[0]], "ingredient_count": 11,
            "ingredients": [s.strip() for s in LABELS[0].split("),")],
            "allergen_statement": "Contains wheat, milk. May contain nuts.",
            "front_claims": CLAIMS, "front_claim_footnotes": [], "extraction_notes": [],
            "confidence": {"ingredients": 0.99, "front_claims": 0.9, "product_identity": 0.5},
        }
        j = c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
                   data={"replay": json.dumps(vision), "avoid": ",".join(ALLERGENS),
                         "profiles": json.dumps(PROFILES)}).json()
        # `reliability` is developer diagnostics; the consumer copy is
        # `disclosures`, `allergens`, `display`, `claim_check` and `screen`.
        consumer = {k: j.get(k) for k in ("disclosures", "allergens", "display", "claim_check", "screen")}
        assert_clean(list(strings(consumer)), f"/scan ({status})")


def test_every_allergen_sentence():
    texts = [AllergenResult(code, state, "lecithin", seen).parent_text(who)
             for code in ALLERGENS
             for state in ("contains", "may_contain", "uncertain", "not_listed", "cannot_confirm")
             for seen in (True, False)
             for who in ("your child", "Riya")]
    assert_clean(texts, "allergens.parent_text")


def test_every_diet_sentence():
    """D-198: every line diet.py can build, for both choices, each state, mark and place."""
    from insidelabel.lenses import diet
    lists = [["Gelatine"], ["Gelling Agent (INS 441)"], ["Colour (INS 120)"], ["Egg Powder"],
             ["Emulsifier (471)"], ["Emulsifier (322)"], ["Chicken Flavour"], ["Onion Powder"], ["Spices"],
             ["Garlic"], ["Masala"], ["Salt"]]
    texts = list(diet.NO_MARK.values()) + [diet.cannot_confirm_both(c) for c in (True, False)]
    for ings in lists:
        for mark in ("veg", "non_veg", "not_visible", None):
            for kw in ({}, {"confidence": 0.5}, {"complete": False}):
                for r in diet.check(ings, list(diet.DIETS), veg_mark=mark, **kw).values():
                    for where in ("photo", "pack"):
                        texts += [diet.text(r, where), diet.mark_note(r, where)]
    assert_clean([t for t in texts if t], "diet.text")


def test_lint_catches_the_diet_words():
    assert hits("Pure veg, Jain-friendly and veg-safe") == ["Pure veg", "Jain-friendly", "veg-safe"]


def test_compare_render():
    packs = [Product(str(i), f"Pack {i}", [s.strip() for s in raw.split(",")],
                     allergen_statement="May contain milk.")
             for i, raw in enumerate(LABELS)]
    for age in ("toddler", "kid", "young"):
        for avoid in ((), ("milk",), ("peanut", "gluten")):
            r = compare(packs, age=age, avoid=avoid)
            text = render(r)
            assert_clean(text.splitlines(), f"compare render age={age} avoid={avoid}")
            for p in packs:
                assert_clean([f.parent_text for f in p.facts], f"compare facts {p.name}")


def test_ingredient_notes_table_and_their_screen_words():
    # D-132: every sentence of data/ingredient_notes.json and the words the screen
    # puts around them. The screen output itself is linted in test_ingredient_notes.py
    # (rows show only once reviewed, so a plain /scan here may not include them).
    from insidelabel.lenses import screen
    with open(os.path.join(ROOT, "data", "ingredient_notes.json"), encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    texts = [t for r in rows for t in [r["title"], *r["summary"]]]
    texts += [screen.NOTES_TITLE, screen.NOTE_MORE, screen.SUGAR_MORE_TITLE]
    assert_clean(texts, "ingredient_notes.json")


def test_nutrition_table_words():
    # D-133: the words the screen puts around a nutrition table. The sentences built
    # from real tables are linted in test_nutrition.py (all six gold labels).
    from insidelabel.lenses import nutrition, screen
    texts = [screen.NUTRITION_TITLE, screen.NUTRITION_MISSING, screen.NUTRITION_UNCLEAR, screen.NUTRITION_PARTIAL,
             screen.NUTRITION_UNVERIFIED, screen.NUTRITION_ASK, screen.NUTRITION_CHECKED, screen.NUTRITION_ADULTS,
             *nutrition.THRESHOLDS["trans_fat_tile"]["summary"]]
    assert_clean(texts, "nutrition table words")


def test_site_pages():
    # D-076: the public pages (home, about, how, privacy) and the app shell are
    # consumer copy too. Tags are stripped; only the words a reader sees are checked.
    import glob
    import html
    pages = sorted(glob.glob(os.path.join(ROOT, "web", "site", "*.html"))) + [os.path.join(ROOT, "web", "index.html")]
    assert len(pages) >= 5
    for p in pages:
        with open(p, encoding="utf-8") as f:
            text = html.unescape(re.sub(r"<[^>]+>", " ", f.read()))
        assert_clean([" ".join(text.split())], os.path.relpath(p, ROOT))


def test_barcode_digit_check_words():
    """D-146: the digit check before the ingredients photo, and the catalogue hit's way back."""
    from insidelabel.lenses import screen
    check = screen.barcode_check("8901499008343")
    assert_clean([check["title"], check["text"], check["yes"], check["again"], screen.RESCAN_TEXT,
                  screen.RESCAN_BUTTON], "barcode digit check")


def test_play_store_listing():
    """D-148: the Play listing in docs/PLAY_RELEASE.md is consumer copy, under the same rules,
    within Play's lengths, and names no brand (D-042) and no retailer (D-088)."""
    path = os.path.join(ROOT, "docs", "PLAY_RELEASE.md")
    with open(path, encoding="utf-8") as f:
        doc = f.read()
    block = doc.split("<!-- play-listing:start -->", 1)[1].split("<!-- play-listing:end -->", 1)[0]
    name = re.search(r"\*\*App name:\*\* (.+)", block).group(1).strip()
    short = re.search(r"\*\*Short description:\*\*\n(.+)", block).group(1).strip()
    full = block.split("**Full description:**", 1)[1].strip()
    assert name == "InsideLabel" and len(name) <= 30
    assert 0 < len(short) <= 80, len(short)
    assert 0 < len(full) <= 4000, len(full)
    assert_clean([name, short, full], "Play store listing")
    brands = ["britannia", "patanjali", "maliban", "limca", "ziggy", "nestle", "amul", "parle",
              "amazon", "flipkart", "blinkit", "zepto", "swiggy", "safelabel", "truthin"]
    named = [b for b in brands if re.search(rf"\b{b}\b", block, re.IGNORECASE)]
    assert not named, f"the listing names {named}"


def test_photo_limit_words():
    """D-148: the daily photo-scan limit screen (lenses/screen.py), for minutes and hours."""
    from insidelabel.lenses import screen
    for seconds in (30, 3600, 86_400):
        assert_clean(list(screen.photo_limit(seconds, 15).values()), "photo limit screen")


# ---------------------------------------------------------------- D-200: infant packs

def test_the_infant_lint_allows_best_only_inside_the_notice_as_printed():
    printed = [INFANT_NOTICE]
    assert infant_hits(f'This pack says "{INFANT_NOTICE}".', printed) == []           # quoted as printed
    assert infant_hits(INFANT_NOTICE, printed) == []                                  # the pack's own words
    assert infant_hits(f'This pack says "{INFANT_NOTICE}".') == ["BEST"]              # not printed on this pack
    assert infant_hits("the best pick of these", printed) == ["best"]                 # our own words
    assert infant_hits(f'"{INFANT_NOTICE}" and the best one', printed) == ["best"]
    assert infant_hits('"MOTHER\'S MILK IS BEST"', printed) == ["BEST"]                # not the exact notice
    assert infant_hits("Suitable for your baby, safe, healthy and recommended", printed) == [
        "Suitable for your baby", "safe", "healthy", "recommended"]
    # D-201's five
    assert infant_hits("High protein, too much sugar; it fails, is not allowed, a violation") == [
        "High", "too much", "fails", "not allowed", "violation"]
    assert infant_hits("Protein: 4.89 g per 100 kcal. FSSAI's range: 2.10 to 3.40 g.") == []


def test_our_own_infant_words_never_use_them():
    from insidelabel.api import main
    from insidelabel.lenses import screen, side_by_side
    ours = [screen.INFANT_NO_TYPE, screen.INFANT_PARTIAL, screen._FREE_FROM_RULE,
            *screen.INFANT_TYPE_WORDS.values(), *screen.INFANT_STATEMENT_NAMES.values(),
            # D-201's words, in place of D-200's INFANT_TEXT and INFANT_TITLES
            screen.INFANT_KIND_LINE, screen.INFANT_WHY_TITLE, screen.INFANT_WHY, screen.INFANT_WORTH_TITLE,
            screen.INFANT_GOOD_TITLE, *screen.INFANT_BLOCK_TITLES.values(), screen.INFANT_RULES_TITLE,
            screen.INFANT_IN_FORCE, screen.INFANT_NO_INS, screen.INFANT_WHICH_TITLE, *screen.INFANT_SIDE.values(),
            main.INFANT_ONE_AT_A_TIME, side_by_side.NO_AGE, side_by_side.NO_SUGAR, side_by_side.NO_ADDED,
            *screen.INFANT_NOT_FOUND.values(), *screen._FREE_FROM_CHIP.values(), *side_by_side.HEADING.values(),
            *side_by_side.NOTE.values(), *side_by_side.TITLES.values(), side_by_side.NOT_READ, side_by_side.NOTHING,
            side_by_side.NO_TYPE, side_by_side.NO_NUMBERS, side_by_side.TYPE_SHORT, side_by_side.NO_TYPE_SHORT,
            *side_by_side.FREE_FROM_WORD.values()]
    assert infant_hits(ours) == []
    assert_clean(ours, "D-200 infant and side-by-side words")


def test_an_infant_result_and_compare_use_none_of_them(infant_on):
    from test_infant_to_users import BOILED, NOTICE, STATEMENTS, _packs, compare, infant, scan
    from test_pack_kind import st
    a = scan(infant("processed_cereal", ingredients=["Wheat flour", "Milk solids", "Vanilla flavour"],
                    extra=[st("ENERGY FOOD", "front")]), key="lint-a")
    b = scan(infant(None, statements=[x for x in STATEMENTS if x["text"] != NOTICE] + [BOILED]), key="lint-b")
    assert infant_hits(a["screen"], printed=[NOTICE]) == []
    assert infant_hits(b["screen"]) == []                     # no notice printed: "best" nowhere at all
    j = compare(_packs(a, b)).json()
    assert infant_hits(j) == []
    assert_clean(list(strings(a["screen"])) + list(strings(j)), "infant result and compare")

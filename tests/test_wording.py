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
FORBIDDEN_SAFETY = ["safe", "safely", "free from", "allergen-free", "allergen free", "healthy"]

_PATTERN = re.compile(
    r"(?<![a-z0-9-])(" + "|".join(re.escape(w) for w in FORBIDDEN + FORBIDDEN_SAFETY) + r")(?![a-z0-9-])",
    re.IGNORECASE,
)

# table -> consumer-facing string fields
CONSUMER_FIELDS = {
    "additives.json": ("additives", ["name", "why"]),
    "nova_markers.json": ("markers", ["name"]),
    "allergens.json": ("allergens", ["label", "short"]),
    "claim_rules.json": ("rules", ["label"]),
}


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

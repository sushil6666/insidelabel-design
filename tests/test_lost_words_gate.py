"""
D-159 (refines D-118, D-157, D-158): /scan asks for a clearer photo only when a
word Cloud Vision read in the ingredient list, and Gemini's list lacks, could
change the user's result. The rules judge (D-004): the scan's own rules run on
the list with and without the lost words. The D-117 review checker stays word
for word strict, so a person still sees every such pack.

Problem report #5 is the case: scan 8bd1c116 (Nestle Choco Coated Wafer, the back
in 3 parts) still lost "choce" and "water" after D-157 and D-158, and the tester
was asked for a clearer photo for two words that change nothing they would see.
"""
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_checker_stamps_and_cuts import GEMINI, PARTS  # noqa: E402

from insidelabel import repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.core.tokenize import ins_numbers  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import checker  # noqa: E402

STATEMENT = "Contains Wheat, Soy, Sesame and Milk."


def vision(ingredients, statement=STATEMENT):
    return json.dumps({
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Nestle", "name": "Choco Coated Wafer", "variant": None, "net_quantity": None,
                    "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": statement,
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}})


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield uri
    main.STORE, main.MEDIA = saved


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def scan(ocr_text, ingredients=GEMINI, **kw):
    """A new pack's back photo, with Cloud Vision's text replayed for it."""
    photo = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    form = {"replay": vision(ingredients, **kw), "barcode": gtin()}
    with cloud_vision.replaying({cloud_vision.digest(photo): ocr_text}):
        return TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")}, data=form)


# ---------------------------------------------------------------- the rules decide

def test_which_lost_words_change_the_result():
    # report #5's list already has "Milk solids" (and its statement says milk), so a lost
    # "milk" changes nothing there; the milk row uses the list without them.
    no_milk = [x for x in GEMINI if x != "Milk solids"]
    assert main.lost_words_matter(no_milk, ["milk"], None) is True          # an allergen
    assert main.lost_words_matter(GEMINI, ["sucralose"], STATEMENT) is True  # an additive finding
    assert main.lost_words_matter(GEMINI, ["glucose"], STATEMENT) is True    # a sugar name
    assert main.lost_words_matter(GEMINI, ["rice"], STATEMENT) is False
    assert main.lost_words_matter(GEMINI, ["water"], STATEMENT) is False
    assert main.lost_words_matter(GEMINI, ["choce", "water"], STATEMENT) is False
    assert main.lost_words_matter(GEMINI, [], STATEMENT) is False


# ---------------------------------------------------------------- the gate

def test_report_5_goes_through_and_the_trace_keeps_the_lost_words(env):
    assert checker.independent_read(GEMINI, PARTS) == (True, [], ["choce", "water"])
    r = scan(PARTS)
    assert r.status_code == 200, r.text
    assert r.json()["screen"]["state"] == "result"
    ocr = q(env, "SELECT ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0][0]
    assert ocr["back"]["independent_read"] == {"section_found": True, "missing": [], "lost": ["choce", "water"],
                                               "lost_ins": [], "asked": False}


def test_a_lost_word_that_matters_still_asks(env):
    text = PARTS.replace("Flour treatment\n(516)", "Flour treatment,\nSucralose (516)")
    assert "sucralose" in checker.independent_read(GEMINI, text)[2]
    r = scan(text)
    assert r.status_code == 422, r.text
    assert r.json()["reliability"]["error"] == "independent_read_failed"
    ocr = q(env, "SELECT ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0][0]
    assert ocr["back"]["independent_read"]["asked"] is True


def test_a_lost_allergen_still_asks(env):
    no_milk = [x for x in GEMINI if x != "Milk solids"]
    r = scan(PARTS, ingredients=no_milk, statement=None)       # Cloud Vision read "Milk solids"
    assert r.status_code == 422, r.text


def test_missing_words_ask_only_when_they_matter(env):
    # D-191 (Sushil, 2026-10-10): words of Gemini's list Cloud Vision never saw get D-159's
    # test too. "Rice bran oil" changes nothing; a "Sucralose" it never saw does (an additive).
    r = scan(PARTS, ingredients=GEMINI + ["Rice bran oil"])
    assert r.status_code == 200, r.text
    r1 = scan(PARTS, ingredients=GEMINI + ["Sucralose"])
    assert r1.status_code == 422, r1.text
    # No list in Cloud Vision's text: Gemini's allergen words aren't in it, so it still asks.
    r2 = scan("Best before 6 months from packaging. Net Weight 100 g.")
    assert r2.status_code == 422, r2.text


def test_the_review_checker_still_sends_report_5_to_a_person():
    draft = {"ingredients": GEMINI, "name": "Choco Coated Wafer", "category": "7.2.1",
             "allergen_statement": STATEMENT}
    out = {c["check"]: c for c in checker.check(draft, {"kind": "new_product", "ocr_text": PARTS})}
    assert out["nothing_lost"]["ok"] is False
    assert "choce, water" in out["nothing_lost"]["detail"]


def test_a_replay_of_a_let_through_scan_gives_the_same_result(env):
    first = scan(PARTS)
    assert first.status_code == 200, first.text
    with psycopg.connect(env) as c:
        cur = c.execute("SELECT * FROM scans WHERE id = %s", (first.json()["scan_id"],))
        row = dict(zip([d.name for d in cur.description], cur.fetchone()))
    out = repro.replay_scan(row, media=main.MEDIA)
    assert out["status"] == 200
    assert repro.compare(repro.summary(first.json()["screen"]), repro.summary(out["screen"])) == []


# ---------------------------------------------------------------- D-160: numbers, phrases, errors

PLAIN = ["Wheat flour", "Sugar", "Edible vegetable oil (palm)", "Cocoa solids", "Salt"]


def with_dropped(x, before="Cocoa solids, "):
    return f"INGREDIENTS: Wheat flour, Sugar, Edible vegetable oil (palm), {before}{x}, Salt."


@pytest.mark.parametrize("dropped, lost, numbers", [
    ("Preservative (211)", ["preservative"], ["211"]),
    ("Antioxidant (319)", ["antioxidant"], ["319"]),
    ("Acidity regulator (INS 330)", ["acidity", "ins", "regulator"], ["330"]),
    ("Raising agents (500(ii), 503(ii))", ["agents", "raising"], ["500", "503"]),
    ("Colour (150d)", ["colour"], ["150d"]),
])
def test_an_additive_dropped_by_its_number(env, dropped, lost, numbers):
    # The advisor's table: on Gemini's list, D-159 found that the first four changed
    # nothing (LOST holds words only, and the class word alone changes nothing). With
    # the lost numbers read by core/tokenize and given to the rules, all five matter.
    text = with_dropped(dropped)
    assert checker.independent_read(PLAIN, text)[2] == lost
    assert checker.lost_ins_numbers(PLAIN, text) == numbers
    assert main.lost_words_matter(PLAIN, lost, None, numbers) is True
    # In a scan, D-093's cross-check has already put the omitted additive back in the
    # list (it reads the same Cloud Vision text first). Where the entry it adds can be
    # read, the result shows the additive and the read is confirmed outright.
    # D-164: nested brackets too. The cross-check used to add "Raising agents (500(ii)" and
    # "(503)", which the engine can't read, so the gate asked (D-160); it now adds the whole
    # "Raising agents (500(ii), 503(ii))", and 500 and 503 are in the result.
    r = scan(text, ingredients=PLAIN, statement=None)
    assert r.status_code == 200, r.text
    assert "model_omitted_additive" in [c["code"] for c in r.json()["reliability"]["caveats"]]
    assert set(numbers) <= ins_numbers(r.json()["extracted"]["ingredients"])
    ocr = q(env, "SELECT ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0][0]
    # Confirmed outright, or (INS 330: the recovered entry reads "(330)", so the word "ins"
    # is still lost) checked and found to change nothing.
    assert ocr["back"].get("independent_read", {}).get("asked", False) is False


def test_a_lost_number_the_cross_check_did_not_recover_asks(env, monkeypatch):
    # The gate's own net, should the cross-check ever not recover one: the number reaches
    # the rules through lost_ins_numbers and the gate asks.
    monkeypatch.setattr(main.ocr_check, "recover_from", lambda result, ingredients: (ingredients, []))
    r = scan(with_dropped("Preservative (211)"), ingredients=PLAIN, statement=None)
    assert r.status_code == 422, r.text
    ocr = q(env, "SELECT ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0][0]
    assert ocr["back"]["independent_read"]["lost_ins"] == ["211"]
    assert ocr["back"]["independent_read"]["asked"] is True


def test_sorted_lost_words_that_form_an_exclude_phrase_still_ask(env):
    # "coconut" + "milk" joined is "coconut milk", in milk's exclude list (allergens.json).
    text = with_dropped("Milk solids", before="Coconut, ")
    text = text.replace("Sugar, Edible", "Sugar, Coconut, Milk solids, Edible").replace("Coconut, Milk solids, Salt", "Salt")
    assert checker.independent_read(PLAIN, text)[2] == ["coconut", "milk"]
    assert scan(text, ingredients=PLAIN, statement=None).status_code == 422
    # "egg" + "free": "egg free" is in egg's exclude list.
    assert main.lost_words_matter(PLAIN, ["egg", "free"]) is True


def test_a_misread_number_that_is_no_additive_goes_through(env):
    # Chosen: the rules decide what a lost number means. "INS 987" is in no table, so it
    # changes nothing and doesn't ask; a bare "(987)" isn't read as a number at all (D-099).
    text = with_dropped("Water (INS 987)")
    assert checker.lost_ins_numbers(PLAIN, text) == ["987"]
    assert main.lost_words_matter(PLAIN, ["ins", "water"], None, ["987"]) is False
    r = scan(text, ingredients=PLAIN, statement=None)
    assert r.status_code == 200, r.text


def test_a_failing_check_asks_and_says_so(env, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("engine down")
    monkeypatch.setattr(main.engine, "ingredient_notes", broken)
    r = scan(PARTS)
    assert r.status_code == 422, r.text
    assert r.json()["reliability"]["error"] == "independent_read_failed"
    assert r.json()["screen"]["can_use_anyway"] is True
    ocr = q(env, "SELECT ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0][0]
    assert ocr["back"]["independent_read"]["error"] is True
    assert ocr["back"]["independent_read"]["asked"] is True

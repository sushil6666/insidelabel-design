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
                                         "asked": False}


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


def test_missing_words_or_no_list_still_ask(env):
    r = scan(PARTS, ingredients=GEMINI + ["Rice bran oil"])    # words Cloud Vision never saw
    assert r.status_code == 422, r.text
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

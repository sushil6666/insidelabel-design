"""
D-175 (Sushil, 2026-10-08; "15 days will keep"): a published pack is checked again
against the real pack every 15 days, without slowing anyone down. The result comes
first; a pack last checked over 15 days ago offers one optional photo of its list.
The photo is compared with the published list for free first (the text Cloud Vision
read from it); only a photo that isn't clearly the same goes on to the paid read,
exactly the normal photo path. Nothing is ever published automatically.

The packs and Cloud Vision texts are the real ones the repo keeps (Maliban wafer,
the item 13 biscuit, the D-157 stamped list).
"""
import datetime as dt
import io
import json
import uuid

import pytest
from PIL import Image

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_checker_stamps_and_cuts import GEMINI, STAMPED  # noqa: E402
from test_review_agents import BISCUIT, BISCUIT_OCR, MALIBAN, MALIBAN_OCR  # noqa: E402

from insidelabel import repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision, gemini  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import checker  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

LIST = MALIBAN["ingredients"]
STATEMENT = MALIBAN["allergen_statement"]
AVOID = [{"ref": "p1", "age": "kid", "avoid": ["peanut"]}]
NO_AVOID = [{"ref": "p1", "age": "kid", "avoid": []}]


def reading(ingredients=LIST, statement=STATEMENT):
    return json.dumps({
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Maliban", "name": "Wafer", "variant": "Cheese Flavour", "net_quantity": None,
                    "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": statement,
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}})


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(fresh_db[0])
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield fresh_db[0]
    main.STORE, main.MEDIA = saved


@pytest.fixture
def no_model(monkeypatch):
    """The free path never calls the model: a live call fails the test (a recorded answer is no call)."""
    calls, real = [], gemini.analyze_images

    def boom(*a, raw_response=None, **k):
        if raw_response is not None:
            return real(*a, raw_response=raw_response, **k)
        calls.append(1)
        raise AssertionError("the model was called")
    monkeypatch.setattr(gemini, "analyze_images", boom)
    return calls


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def photo():
    return b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes


def real_photo():
    """A photo the D-103 check accepts: without a recorded model answer, it runs."""
    buf = io.BytesIO()
    Image.effect_noise((1200, 900), 60).convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


def published(env, days_ago=0):
    """A barcode published with Maliban's list, its check `days_ago` days old."""
    bc = gtin()
    with cloud_vision.replaying({}):
        r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")},
                                      data={"replay": reading(), "barcode": bc})
    assert r.status_code == 200, r.text
    item = q(env, """SELECT q.id FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s""", bc)[0][0]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(item, "sushil")
    svc.approve(item, "sushil", {"name": "Wafer", "brand": "Maliban", "category": "7.2.1",
                                 "ingredients": "\n".join(LIST), "allergen_statement": STATEMENT})
    age(env, bc, days_ago)
    return bc


def age(env, bc, days, photo_days=None):
    with psycopg.connect(env) as c:
        c.execute("""UPDATE product_versions v SET verified_at = now() - make_interval(days => %s),
                            last_verified_at = CASE WHEN %s::int IS NULL THEN NULL
                                                    ELSE now() - make_interval(days => %s::int) END
                       FROM products p WHERE p.id = v.product_id AND p.barcode = %s AND v.is_current""",
                  (days, photo_days, photo_days, bc))


def version(env, bc):
    return q(env, """SELECT v.id, v.last_verified_at, v.version_no FROM product_versions v
                       JOIN products p ON p.id = v.product_id WHERE p.barcode = %s AND v.is_current""", bc)[0]


def lookup(bc, profiles=NO_AVOID):
    r = TestClient(main.app).post("/scan", data={"barcode": bc, "profiles": json.dumps(profiles)})
    assert r.status_code == 200, r.text
    return r.json()


def recheck(bc, text, model=None, profiles=NO_AVOID):
    """A re-check photo, with Cloud Vision's text replayed for it; `model` a recorded reading."""
    data = {"barcode": bc, "recheck": "true", "profiles": json.dumps(profiles), "back_source": "live"}
    if model is not None:
        data["replay"] = model
    pic = photo() if model is not None else real_photo()
    with cloud_vision.replaying({cloud_vision.digest(pic): text}):
        return TestClient(main.app).post("/scan", files={"back": ("b.jpg", pic, "image/jpeg")}, data=data)


def items_for(env, bc):
    return q(env, """SELECT q.kind FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s AND q.status = 'open'""", bc)


def today():
    return screen._day(dt.datetime.now(dt.timezone.utc).date().isoformat())


# ---------------------------------------------------------------- the free rule

def test_the_real_packs_and_the_measured_cases():
    assert checker.unchanged(LIST, STATEMENT, MALIBAN_OCR)["decision"] == "unchanged"
    assert checker.unchanged(BISCUIT, None, BISCUIT_OCR)["decision"] == "unchanged"
    # D-157's stamped pack prints entries without commas: 8 entries against 11. Not clear,
    # which only costs the paid read.
    r = checker.unchanged(GEMINI, "Contains Wheat, Soy Sesame and Milk", STAMPED)
    assert r["decision"] == "not_clear" and (r["entries"], r["stored_entries"]) == (8, 11)
    for packs in ((LIST, STATEMENT, MALIBAN_OCR), (BISCUIT, None, BISCUIT_OCR)):
        ings, stmt, text = packs
        for i in range(len(ings)):                      # the pack gained one entry
            assert checker.unchanged(ings[:i] + ings[i + 1:], stmt, text)["decision"] == "not_clear", ings[i]
        for i in range(len(ings) - 1):                  # two neighbouring entries swapped
            swapped = ings[:i] + [ings[i + 1], ings[i]] + ings[i + 2:]
            assert checker.unchanged(swapped, stmt, text)["decision"] == "not_clear", ings[i]


def test_sugar_added_beside_invert_sugar_is_caught_by_the_count():
    # The known miss of the first rule: every word of "Sugar" is in the list already.
    no_sugar = [x for x in BISCUIT if x != "SUGAR"]
    r = checker.unchanged(no_sugar, None, BISCUIT_OCR)
    assert (r["missing"], r["lost"], r["lost_ins"], r["new_allergens"]) == ([], [], [], [])
    assert r["decision"] == "not_clear" and (r["entries"], r["stored_entries"]) == (12, 11)


def test_a_new_number_allergen_or_word_is_not_clear():
    def text(old, new):
        return MALIBAN_OCR.replace(old, new)
    r = checker.unchanged(LIST, STATEMENT, text("ACIDITY REGULATOR (270)", "ACIDITY REGULATOR (270, 211)"))
    assert r["lost_ins"] == ["211"] and r["decision"] == "not_clear"
    r = checker.unchanged(LIST, STATEMENT, text("CONTAINS WHEAT, SOY, MILK.", "CONTAINS WHEAT, SOY, MILK, PEANUT."))
    assert r["new_allergens"] == ["peanut"] and r["decision"] == "not_clear"
    r = checker.unchanged(LIST, STATEMENT, text("WHEY,", "WHEY (MALTED BARLEY),"))
    assert r["decision"] == "not_clear"
    # No list end in the text: where the list stops wasn't found.
    r = checker.unchanged(LIST, STATEMENT, MALIBAN_OCR.split("ACIDITY")[0])
    assert r["list_end_found"] is False and r["decision"] == "not_clear"
    assert checker.unchanged(LIST, STATEMENT, "Net Weight 100 g")["decision"] == "not_clear"


# ---------------------------------------------------------------- the card

def test_the_card_after_15_days_and_not_before(env):
    bc = published(env, days_ago=14)
    s = lookup(bc)
    assert "recheck_card" not in s["screen"] and s["catalogue"]["recheck_due"] is False
    age(env, bc, 16)
    j = lookup(bc)
    assert j["screen"]["recheck_card"] == screen.RECHECK_CARD
    assert j["screen"]["recheck_card"]["text"] == "Help keep this pack up to date: one photo of the ingredient list."
    assert j["screen"]["recheck_card"]["button"] == "Photograph the ingredient list"
    # One ask per scan: the table and front offers wait for a later scan.
    assert j["catalogue"]["table_wanted"] is False and j["catalogue"]["front_wanted"] is False
    assert "table_offer" not in j["screen"]
    assert screen.RECHECK_AFTER_DAYS == 15


def test_the_avoid_list_ask_wins_and_a_photo_scan_has_no_card(env):
    bc = published(env, days_ago=30)
    s = lookup(bc, profiles=AVOID)["screen"]
    assert s["recheck"] and "recheck_card" not in s                       # D-073 does the same job
    with cloud_vision.replaying({}):
        r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")},
                                      data={"replay": reading(), "barcode": gtin()})
    assert r.status_code == 200 and "recheck_card" not in r.json()["screen"]


# ---------------------------------------------------------------- a matching photo, free

def test_a_matching_photo_costs_no_model_call_and_changes_nothing_else(env, no_model):
    bc = published(env, days_ago=20)
    vid, before, n = version(env, bc)
    assert before is None
    r = recheck(bc, MALIBAN_OCR)
    assert r.status_code == 200, r.text
    j = r.json()
    assert not no_model
    assert next(iter(j)) == "allergens"                                    # D-060
    assert j["catalogue"]["recheck"] == "unchanged" and j["catalogue"]["product_version_id"] == vid
    assert j["screen"]["rechecked"] == f"Pack checked again on {today()}."
    assert "recheck_card" not in j["screen"] and "table_offer" not in j["screen"]       # one ask per scan
    vid2, after, n2 = version(env, bc)
    assert (vid2, n2) == (vid, n) and after is not None
    row = q(env, "SELECT resolved_via, cache_hit, outcome, ai_cost_paise, ocr, request FROM scans WHERE id = %s",
            j["scan_id"])[0]
    assert row[:4] == ("recheck", True, "verdict", 0)
    assert row[4]["back"]["recheck"]["decision"] == "unchanged" and row[4]["back"]["text"] == MALIBAN_OCR
    assert row[5]["recheck"] is True
    assert items_for(env, bc) == []
    # The next hit within 15 days: no card, and both dates, apart.
    s = lookup(bc)
    assert "recheck_card" not in s["screen"]
    assert s["catalogue"]["last_verified"] == after.date().isoformat()
    team = screen._day(s["catalogue"]["team_verified"])
    assert s["screen"]["last_verified"] == (f"Our team checked this label on {team}; "
                                            f"a photo of the pack matched it on {today()}.")
    assert s["disclosures"][0].startswith(f"Our team checked this label on {team}; a photo of the pack")


def test_the_d073_avoid_list_recheck_goes_free_first(env, no_model):
    bc = published(env, days_ago=2)
    assert lookup(bc, profiles=AVOID)["screen"]["recheck"]
    r = recheck(bc, MALIBAN_OCR, profiles=AVOID)
    assert r.status_code == 200, r.text
    assert r.json()["catalogue"]["recheck"] == "unchanged" and not no_model
    assert r.json()["allergens"]["avoid"] == ["peanut"]


# ---------------------------------------------------------------- not clear: the paid read

def test_an_extra_number_goes_to_the_paid_read_and_a_new_list_to_review(env):
    bc = published(env, days_ago=20)
    vid = version(env, bc)[0]
    text = MALIBAN_OCR.replace("ACIDITY REGULATOR (270)", "ACIDITY REGULATOR (270), PRESERVATIVE (211)")
    new = LIST[:10] + ["PRESERVATIVE (211)", LIST[10]]
    r = recheck(bc, text, model=reading(new))
    assert r.status_code == 200, r.text
    row = q(env, "SELECT resolved_via, ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0]
    assert row[0] == "new_product"
    assert row[1]["back"]["recheck"]["decision"] == "not_clear"
    assert row[1]["back"]["recheck"]["lost_ins"] == ["211"]
    assert ("reformulation",) in items_for(env, bc)
    assert version(env, bc)[0] == vid and version(env, bc)[1] is None   # nothing published


def test_an_extra_allergen_with_the_same_list_sets_the_date(env):
    bc = published(env, days_ago=20)
    text = MALIBAN_OCR.replace("CONTAINS WHEAT, SOY, MILK.", "CONTAINS WHEAT, SOY, MILK, PEANUT.")
    r = recheck(bc, text, model=reading())                     # the model reads the same list
    assert r.status_code == 200, r.text
    row = q(env, "SELECT resolved_via, ocr FROM scans WHERE id = %s", r.json()["scan_id"])[0]
    assert row[0] == "barcode" and row[1]["back"]["recheck"]["new_allergens"] == ["peanut"]
    assert version(env, bc)[1] is not None and items_for(env, bc) == []


# ---------------------------------------------------------------- replay

def test_a_free_recheck_replays_with_the_same_decision_and_no_model(env, no_model):
    bc = published(env, days_ago=20)
    first = recheck(bc, MALIBAN_OCR)
    assert first.status_code == 200, first.text
    with psycopg.connect(env) as c:
        cur = c.execute("SELECT * FROM scans WHERE id = %s", (first.json()["scan_id"],))
        row = dict(zip([d.name for d in cur.description], cur.fetchone()))
    hit = main.STORE.version_hit(row["product_version_id"])
    out = repro.replay_scan(row, media=main.MEDIA, hit=hit)
    assert out["status"] == 200 and out["recheck"]["decision"] == "unchanged" and not no_model
    assert out["screen"]["rechecked"] == first.json()["screen"]["rechecked"]
    assert repro.compare(repro.summary(first.json()["screen"]), repro.summary(out["screen"])) == []


def test_a_paid_recheck_replays_with_its_flag(env):
    assert repro.form_for({"recheck": True}, "{}")["recheck"] == "true"


def test_a_failed_paid_read_still_keeps_what_the_free_check_saw(env, monkeypatch):
    bc = published(env, days_ago=20)

    def busy(*a, raw_response=None, **k):
        raise gemini.VisionUnavailable("busy")
    monkeypatch.setattr(gemini, "analyze_images", busy)
    text = MALIBAN_OCR.replace("WHEY,", "WHEY, PEANUT,")
    r = recheck(bc, text)
    assert r.status_code == 503, r.text
    row = q(env, """SELECT outcome, ocr FROM scans WHERE (request->>'recheck')::boolean
                     AND outcome = 'vision_unavailable' ORDER BY created_at DESC LIMIT 1""")[0]
    assert row[1]["back"]["recheck"]["decision"] == "not_clear"
    assert row[1]["back"]["recheck"]["text"] == text
    assert version(env, bc)[1] is None

# ---------------------------------------------------------------- the count, on the server's packs

# D-175 follow-up (2026-10-08): `tools/recheck_measure.py` on the server's 57 published packs
# passed 20; 28 failed on the entry count. Three of them, as stored and as Cloud Vision read
# them (cut at 600 characters from "ingredients"). The stored Oats list splits its chocolate
# chips into parts; Oreo's text drops a bracket ("(500(ii), 503 (ii), STARCH"); Eat Fit's text
# lost commas ("WHEY POWDER WHITE CUMIN").
OATS = ["WHEAT FLOUR (ATTA) (31.3%)", "ROLLED OATS (20.3%)", "SUGAR", "REFINED PALM OIL", "PLAIN CHOCOLATE CHIPS (6.2%) {SUGAR", "COCOA SOLIDS", "COCOA BUTTER", "DEXTROSE", "EMULSIFIER [LECITHIN (FROM SOYBEAN)]", "NATURAL FLAVOURS AND NATURAL FLAVOURING SUBSTANCES}", "LIQUID GLUCOSE", "INVERT SYRUP", "RAISING AGENTS [503(ii), 500(ii), 450(i)]", "COCOA SOLIDS (1.4%)", "ALMOND BITS (1.4%)", "MALTODEXTRIN", "IODIZED SALT", "ARTIFICIAL FLAVOURING SUBSTANCES (MILK, VANILLA) AND EMULSIFIER [LECITHIN (FROM SOYBEAN)]"]
OATS_OCR = """Ingredients
WHEAT FLOUR (ATTA) (31.3%), ROLLED OATS (20.3%), SUGAR, REFINED PALM OIL, PLAIN
CHOCOLATE CHIPS (6.2%) (SUGAR, COCOA SOLIDS, COCOA BUTTER, DEXTROSE, EMULSIFIER
LECITHIN (FROM SOYBEAN)], NATURAL FLAVOURS AND NATURAL FLAVOURING
SUBSTANCES, LIQUID GLUCOSE, INVERT SYRUP, RAISING AGENTS [503(ii), 500(ii), 450(6)],
COCOA SOLIDS (1.4%), ALMOND BITS (1.4%), MALTODEXTRIN, IODIZED SALT, ARTIFICIAL
FLAVOURING SUBSTANCES (MILK, VANILLA) AND EMULSIFIER [LECITHIN (FROM SOYABEAN)].
CONTAINS WHEAT, OATS, SOY, NUT. MAY CONTAIN SULPHITE, MILK.
NUTRITIONAL INFORMATION (APPROX. VALUES): PER 100 g (% R"""
EATFIT = ["REFINED WHEAT FLOUR (MAIDA) (68.3%)", "EDIBLE VEGETABLE OIL [PALM, PALMOLEIN, ANTIOXIDANT (319)]", "HYDROGENATED VEGETABLE OIL (PALM, PALMOLEIN)", "YEAST", "MALT", "WHEY POWDER", "WHITE CUMIN (SAFED JEERA )(0.7%)", "BLACK CUMIN ( KALONJI ) (0.28%)", "CHILLI (0.16%)", "CAROM SEED (AJWAIN) (0.18%)", "MUSTARD(0.10%)", "FENUGREEK LEAVES (0.06%)", "EDIBLE STARCH (CORN)", "SALT", "DOUGH CONDITIONER (223)", "RAISING AGENTS [500(ii), 503(ii)]", "EMULSIFIER [450(i)] & FLOUR TREATMENT AGENT (1101) NUMBERS IN BRACKETS ARE AS PER INTERNATIONAL NUMBERING SYSTEM"]
EATFIT_OCR = """INGREDIENTS:REFINED WHEAT FLOUR (MAIDA) (68.3%), EDIBLE VEGETABLE OIL PALM, PALMOLEIN.
ANTIOXIDANT (319)], HYDROGENATED VEGETABLE OIL (PALM, PALMOLEIN), YEAST, MALT, WHEY POWDER
WHITE CUMIN (SAFED JEERA ) (0.7%) BLACK CUMIN (KALONJI) (0.28%), CHILLI (0.16%), CAROM SEED (AJWAN
(0.18%), MUSTARD (0.10%), FENUGREEK LEAVES (0.06%), EDIBLE STARCH (CORN), SALT, DOUGH CONDITIONER
(223), RAISING AGENTS [500(ii), 503 (ii)], EMULSIFIER [450(i)) & FLOUR TREATMENT AGENT (1101)
NUMBERS IN BRACKETS ARE AS PER INTERNATIONAL NUMBERING SYSTEM
CONTAINS WHEAT AND MILK HYPERSENSITIVE INGREDIENTS
FOR COMPLAINTS/SUG"""
OREO = ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR", "FRACTIONATED FAT", "PALMOLEIN", "INVERT SUGAR", "COCOA SOLIDS (2%*)", "LEAVENING AGENTS (500(ii), 503(ii))", "STARCH", "IODISED SALT", "EMULSIFIER (322)", "NATURE IDENTICAL FLAVOURING SUBSTANCES"]
OREO_OCR = """Ingredients
Oreo cookies 36
Brick cream cheese
(softened)-1 packet (225 g)
Melted chocolate-500 g
Instructions
Crush the Oreo cookies to fine
Mix cream cheese and powdered Oreos
Form 40-50 smooth balls by rolling the
mixture between your palms
Freeze the balls for 10 min
Dip the frozen balls in melted chocolate
the chocolate-dinned hallinnon
AD
TOT
SANDWICH BISCUIT
INGREDIENTS: REFINED WHEAT FLOUR (MAIDA), SUGAR, FRACTIONATED FAT, PALMOLEIN, INVERT
SUGAR, COCOA SOLIDS (2%*), LEAVENING AGENTS (500(ii), 503 (ii), STARCH, IODISED SALT,
EMULSIFIER (322), NATURE IDENTICAL FLAVOURING SUBSTANCES.
ALL"""


def test_a_stored_list_split_inside_brackets_counts_as_printed():
    r = checker.unchanged(OATS, "CONTAINS WHEAT, OATS, SOY, NUT. MAY CONTAIN SULPHITE, MILK.", OATS_OCR)
    assert r["decision"] == "unchanged", r
    assert r["entries"] == r["stored_entries"]


def test_a_dropped_bracket_no_longer_merges_the_rest():
    r = checker.unchanged(OREO, None, OREO_OCR)
    assert r["entries"] == r["stored_entries"] == 12 and not r["out_of_order"]


def test_lost_commas_still_go_to_the_paid_read():
    r = checker.unchanged(EATFIT, "CONTAINS WHEAT AND MILK", EATFIT_OCR)
    assert r["decision"] == "not_clear" and r["entries"] < r["stored_entries"]


def test_the_server_packs_still_catch_an_added_or_swapped_entry():
    for ings, stmt, text in ((OATS, "CONTAINS WHEAT, OATS, SOY, NUT. MAY CONTAIN SULPHITE, MILK.", OATS_OCR),
                             (LIST, STATEMENT, MALIBAN_OCR), (BISCUIT, None, BISCUIT_OCR)):
        for i in range(len(ings)):
            assert checker.unchanged(ings[:i] + ings[i + 1:], stmt, text)["decision"] == "not_clear", ings[i]
        for i in range(len(ings) - 1):
            swapped = ings[:i] + [ings[i + 1], ings[i]] + ings[i + 2:]
            assert checker.unchanged(swapped, stmt, text)["decision"] == "not_clear", ings[i]


def test_a_nutrition_number_is_no_new_allergen():
    # The server's first run (2026-10-08): Junior Horlicks and two more read as "sulphite", from
    # panel values in sulphite's INS range (220 to 228). A new sulphite in the list still counts.
    from insidelabel.lenses import allergens
    assert allergens.mentioned("Energy 225 kcal, Sodium 220 mg") == set()
    text = MALIBAN_OCR.replace("NUTRITIONAL FACTS:", "NUTRITIONAL FACTS: ENERGY 225 KCAL")
    assert checker.unchanged(LIST, STATEMENT, text)["decision"] == "unchanged"
    added = MALIBAN_OCR.replace("ACIDITY REGULATOR (270)", "ACIDITY REGULATOR (270), PRESERVATIVE (223)")
    r = checker.unchanged(LIST, STATEMENT, added)
    assert r["decision"] == "not_clear" and r["lost_ins"] == ["223"]
    assert "sulphite" in allergens.mentioned("Preservative (sodium metabisulphite)")


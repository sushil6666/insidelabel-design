"""
A photo of a screen is read, not refused (D-130, amends D-103).

Sushil, 2026-09-29, from problem report #1 ("Why photo not allowed?"): a user
planning a shop from a laptop or a phone listing should get a result, marked
"read from a screen". A listing can be older than the pack in the shop, so:
the result says where it came from; every allergen line says "on this screen"
and "check the pack"; when our catalogue has the same barcode (read from a
real pack) its allergens are set beside the screen's (case A: the pack lists
what the screen doesn't; case B: they agree; case C: no pack). A listing is a
lead, never the record (D-089): no product, version or review item.
"""
import base64
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel import repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.lenses import screen as result_screen  # noqa: E402

import test_wording  # noqa: E402

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
KID = [{"ref": "p1", "age": "kid", "avoid": ["milk", "soy"]}]
ME = [{"ref": "me", "age": "adult", "avoid": ["milk"]}]
NO_MILK = ["Wheat flour", "Sugar", "Palm oil", "Salt"]
MILK = ["Wheat flour", "Sugar", "Palm oil", "Milk solids", "Salt"]


def gtin():
    body = "890" + str(uuid.uuid4().int)[:9]
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def vision(ingredients, seen="screen", statement=None, **kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "image_content": {"back": seen, "front": "not_provided"},
         "product": {"brand": "Testco", "name": f"Biscuit {uuid.uuid4().hex[:6]}", "variant": None,
                     "net_quantity": None, "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
         "ingredients": ingredients, "allergen_statement": statement,
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def env(fresh_db):
    uri = fresh_db[0]
    saved = main.STORE
    main.STORE = Store(uri)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    yield uri
    mp.undo()
    main.STORE = saved


def counts(uri):
    with psycopg.connect(uri) as conn:
        return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                     for t in ("products", "product_versions", "review_queue"))


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def scan(v, barcode=None, profiles=KID):
    data = {"replay": v, "profiles": json.dumps(profiles)}
    if barcode:
        data["barcode"] = barcode
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")}, data=data)


def published(uri, ingredients, statement=None):
    """A pack in the catalogue, read from a real one and published by a person."""
    bc = gtin()
    j = scan(vision(ingredients, seen="food_pack", statement=statement), barcode=bc).json()
    with psycopg.connect(uri) as conn:
        conn.execute("SELECT publish_version(%s, 'tester')", (j["catalogue"]["product_version_id"],))
    return bc


# ---------------------------------------------------------------- read, marked, never catalogued

def test_a_screen_is_read_and_says_so(env):
    before = counts(env)
    r = scan(vision(NO_MILK), barcode=gtin())
    assert r.status_code == 200
    j = r.json()
    s = j["screen"]
    assert s["state"] == "result"
    assert s["from_screen"]["title"] == "Read from a screen, not the pack."
    assert "Check the pack in the shop" in s["from_screen"]["text"]
    assert s["shop_list"] is True
    assert j["reliability"]["from_screen"] is True
    assert any(cv["code"] == "read_from_screen" for cv in j["reliability"]["caveats"])
    assert j["allergens"]["source"] == "screen"
    # D-089: nothing enters the catalogue, even with a barcode.
    assert counts(env) == before
    assert j["catalogue"] == {"source": "screen", "status": "not_saved", "reason": "from_screen",
                              "pack_verified_on": None}
    sc = row(env, "SELECT * FROM scans WHERE id = %s", j["scan_id"])
    assert sc["outcome"] == "screen_read" and sc["resolved_via"] == "screen"
    assert sc["product_version_id"] is None
    assert sc["model_raw"] is not None                                  # D-092: replayable


def test_a_screen_read_replays_to_the_same_screen(env):
    first = scan(vision(NO_MILK), barcode=gtin()).json()
    s = row(env, "SELECT * FROM scans WHERE id = %s", first["scan_id"])
    out = repro.replay_scan(s, media=None)
    assert out["status"] == 200
    assert repro.summary(out["screen"]) == repro.summary(first["screen"])


def test_a_screen_without_a_barcode_is_read_too(env):
    j = scan(vision(NO_MILK)).json()
    assert j["screen"]["from_screen"] and j["catalogue"]["reason"] == "from_screen"


def test_no_clearer_photo_request_for_a_screen(env, monkeypatch):
    # D-118 asks only for packs that would join the catalogue; a screen never does.
    monkeypatch.setattr(main.ocr_check, "cloud_first", lambda: False)
    j = scan(vision(NO_MILK), barcode=gtin()).json()
    assert j["screen"]["state"] == "result" and "can_use_anyway" not in j["screen"]


def test_an_unreadable_screen_is_a_plain_retake_not_send_it_to_us(env):
    r = scan(vision([], back_status="unreadable", ingredients_status="unreadable"), barcode=gtin())
    assert r.status_code == 422
    s = r.json()["screen"]
    assert s["headline"]["text"] == result_screen.SCREEN_HEADLINE_UNREAD
    assert s["retake"] == result_screen.SCREEN_RETAKE and s["can_send"] is False


def test_a_pack_photo_is_unchanged(env):
    j = scan(vision(NO_MILK, seen="food_pack"), barcode=gtin()).json()
    assert "from_screen" not in j["screen"] and "shop_list" not in j["screen"]
    assert j["catalogue"]["source"] == "scan"


# ---------------------------------------------------------------- allergen lines: cases A, B, C

def test_case_c_no_pack_no_match_shows_nothing_and_the_screen_card_cautions(env):
    # D-188 (option B): no match, no line; the from_screen card says to check the pack in the shop.
    s = scan(vision(NO_MILK), barcode=gtin()).json()["screen"]
    assert s["people"] == [] and "for_you" not in s
    assert s["from_screen"]["text"] == result_screen.SCREEN_TEXT
    assert "Check the pack in the shop before you buy." in s["from_screen"]["text"]


def test_case_c_for_your_own_list(env):
    s = scan(vision(NO_MILK), barcode=gtin(), profiles=ME).json()["screen"]
    assert s["people"] == [] and "for_you" not in s


def test_what_the_screen_lists_is_shown_as_the_screen_says(env):
    [p] = scan(vision(MILK), barcode=gtin()).json()["screen"]["people"]
    assert p["status"] == "contains"
    assert p["line"] == "Contains milk, as listed on this screen. It's on {name}'s avoid list."


def test_case_a_the_pack_lists_what_an_old_listing_does_not(env):
    # Sushil's example: the listing photo is from before the recipe added milk.
    bc = published(env, MILK, statement="Contains wheat, milk.")
    j = scan(vision(NO_MILK), barcode=bc).json()
    [p] = j["screen"]["people"]
    day = result_screen._day(j["catalogue"]["pack_verified_on"])
    assert p["status"] == "contains"
    assert p["line"] == (f"Milk: listed on the pack we checked on {day}. "
                         f"This screen doesn't show it, so the listing may be old.")
    assert j["screen"]["from_screen"]["pack"].startswith(f"We also checked this pack in a shop on {day}")


def test_case_b_the_pack_and_the_screen_agree(env):
    # D-188 (option B): they agree nothing on the avoid list is listed: no line; the card names the pack's day.
    bc = published(env, NO_MILK, statement="Contains wheat.")
    j = scan(vision(NO_MILK), barcode=bc).json()
    day = result_screen._day(j["catalogue"]["pack_verified_on"])
    assert j["screen"]["people"] == []
    assert j["screen"]["from_screen"]["pack"].startswith(f"We also checked this pack in a shop on {day}")


def test_a_low_confidence_screen_read_cannot_confirm(env):
    # D-060 still applies: below 0.95 nothing is "not listed".
    v = vision(NO_MILK, confidence={"ingredients": 0.8, "front_claims": 0.0, "product_identity": 0.5})
    [p] = scan(v, barcode=gtin()).json()["screen"]["people"]
    assert p["status"] == "cannot_confirm" and "on this screen" in p["line"]


def test_screen_texts_pass_the_wording_lint(env):
    texts = [result_screen.SCREEN_TITLE, result_screen.SCREEN_TEXT, result_screen.SCREEN_NOTE,
             result_screen.SCREEN_PACK, result_screen.SCREEN_HEADLINE_UNREAD, result_screen.SCREEN_RETAKE]
    for ings in (NO_MILK, MILK):
        j = scan(vision(ings), barcode=gtin()).json()
        texts += [p["line"] for p in j["screen"]["people"]]
        texts += [a["text"] for p in j["screen"]["people"] for a in p["allergens"]]
    test_wording.assert_clean(texts, "screen-read texts")


def test_day_format():
    assert result_screen._day("2026-08-12") == "12 Aug 2026"


# ---------------------------------------------------------------- in the shop: the pack against the screenshot

def shop_scan(v, screen_pack, barcode=None, photo=True, profiles=KID):
    data = {"screen_pack": json.dumps(screen_pack), "profiles": json.dumps(profiles)}
    if v:
        data["replay"] = v
    if barcode:
        data["barcode"] = barcode
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")} if photo else None, data=data)


SHOT = {"ingredients": NO_MILK, "allergen_statement": None}


def test_the_pack_in_the_shop_says_what_the_screenshot_missed(env):
    j = shop_scan(vision(MILK, seen="food_pack"), SHOT, barcode=gtin()).json()
    since = j["screen"]["since_screen"]
    assert since["title"] == "Compared with your screenshot" and since["differs"] is True
    assert since["lines"] == ["Milk is listed on this pack. The screenshot didn't list it."]
    s = row(env, "SELECT request FROM scans WHERE id = %s", j["scan_id"])
    assert s["request"]["screen_pack"] == SHOT                          # D-092: replayable


def test_a_catalogue_lookup_from_the_shop_list_compares_too(env):
    bc = published(env, MILK, statement="Contains wheat, milk.")
    j = shop_scan(None, SHOT, barcode=bc, photo=False).json()
    assert j["screen"]["since_screen"]["lines"] == ["Milk is listed on this pack. The screenshot didn't list it."]


def test_when_nothing_differs_it_says_so(env):
    j = shop_scan(vision(NO_MILK, seen="food_pack"), SHOT, barcode=gtin()).json()
    assert j["screen"]["since_screen"] == {"title": "Compared with your screenshot", "differs": False,
                                           "lines": [result_screen.SINCE_SAME]}


def test_a_shop_list_scan_replays_with_its_comparison(env):
    first = shop_scan(vision(MILK, seen="food_pack"), SHOT, barcode=gtin()).json()
    s = row(env, "SELECT * FROM scans WHERE id = %s", first["scan_id"])
    out = repro.replay_scan(s, media=None)
    assert out["screen"]["since_screen"] == first["screen"]["since_screen"]


@pytest.mark.parametrize("bad", ["not json", json.dumps({"ingredients": "Sugar"}), json.dumps({"x": 1}),
                                 json.dumps({"ingredients": []})])
def test_a_bad_screen_pack_is_refused(env, bad):
    r = c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
               data={"replay": vision(NO_MILK, seen="food_pack"), "screen_pack": bad})
    assert r.status_code == 422 and r.json()["error"] == "bad_screen_pack"


def test_comparison_texts_pass_the_wording_lint(env):
    texts = [result_screen.SINCE_TITLE, result_screen.SINCE_SAME, result_screen.SINCE_UNREAD]
    for now, then in ((MILK, NO_MILK), (NO_MILK, MILK)):
        j = shop_scan(vision(now, seen="food_pack"), {"ingredients": then, "allergen_statement": None},
                      barcode=gtin()).json()
        texts += j["screen"]["since_screen"]["lines"]
    test_wording.assert_clean(texts, "comparison texts")

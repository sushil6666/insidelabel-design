"""
A pack without a barcode (D-107): the user still gets the result from the
ingredients photo, but nothing enters the catalogue. The catalogue is filed by
barcode (D-024); without one, a record can't be found again or kept apart from
other packs. The scan row itself is kept (D-092: it can be replayed), and its
photos go at 30 days (D-098) because no version holds them.
"""
import base64
import json
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel import repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.review.service import ReviewError, ReviewService  # noqa: E402

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def gtin():
    body = "890" + str(uuid.uuid4().int)[:9]
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": f"Loose {uuid.uuid4().hex[:6]}", "variant": None,
                     "net_quantity": None, "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": ["Wheat flour, Sugar, Milk solids"], "ingredient_count": 3,
         "ingredients": ["Wheat flour", "Sugar", "Milk solids"], "allergen_statement": "Contains wheat, milk.",
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
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri
    mp.undo()
    main.STORE = saved


def counts(uri):
    with psycopg.connect(uri) as conn:
        return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                     for t in ("products", "product_versions", "review_queue"))


def scan(barcode=None, **v):
    data = {"replay": vision(**v)}
    if barcode:
        data["barcode"] = barcode
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")}, data=data)


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def test_no_barcode_gives_a_result_but_no_catalogue_entry(env):
    before = counts(env)
    r = scan()
    assert r.status_code == 200
    j = r.json()
    assert j["verdict"] is not None and j["screen"]["state"] == "result"
    assert j["catalogue"] == {"source": "scan", "status": "not_saved", "reason": "no_barcode"}
    assert counts(env) == before                                   # no product, version or review item
    s = row(env, "SELECT * FROM scans WHERE id = %s", j["scan_id"])
    assert s["outcome"] == "unlisted" and s["product_version_id"] is None
    assert s["model_raw"]                                           # replayable (D-092)


def test_the_screen_says_it_was_not_added(env):
    note = scan().json()["screen"]["catalogue_note"]
    assert "barcode" in note.lower()
    import test_wording
    test_wording.assert_clean([note], "catalogue note")


def test_with_a_barcode_the_pack_goes_to_review_as_before(env):
    before = counts(env)
    r = scan(barcode=gtin())
    assert r.status_code == 200 and r.json()["catalogue"]["queued_for_review"] == "new_product"
    assert counts(env) == (before[0] + 1, before[1] + 1, before[2] + 1)
    # Not the no-barcode note; since D-167, the note a pack we haven't checked yet gets.
    from insidelabel.lenses import screen
    assert r.json()["screen"]["catalogue_note"] == screen.UNCHECKED_NOTE != screen.UNLISTED_NOTE


def test_an_unlisted_scan_can_be_replayed(env):
    j = scan().json()
    s = row(env, "SELECT * FROM scans WHERE id = %s", j["scan_id"])
    out = repro.replay_scan(s, media=None)
    assert out["status"] == 200 and repro.summary(out["screen"]) == repro.summary(j["screen"])


def test_a_refusal_without_a_barcode_cannot_be_sent_to_us(env):
    r = scan(back_status="unreadable", ingredients_status="unreadable", ingredients=[])
    assert r.status_code == 422 and r.json()["screen"]["can_send"] is False
    r = scan(barcode=gtin(), back_status="unreadable", ingredients_status="unreadable", ingredients=[])
    assert r.json()["screen"]["can_send"] is True


def test_the_server_refuses_to_queue_packs_without_a_barcode(env):
    dev = str(uuid.uuid4())
    ids = [c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
                  data={"replay": vision(back_status="unreadable", ingredients_status="unreadable", ingredients=[]),
                        "device_id": dev}).json()["scan_id"] for _ in range(2)]
    r = c.post("/send-to-us", json={"device_id": dev, "scan_ids": ids})
    assert r.status_code == 422 and r.json()["error"] == "no_barcode"


def test_a_reviewer_cannot_create_a_product_without_a_barcode(env):
    sid = scan().json()["scan_id"]
    rid = c.post("/report", json={"scan_id": sid, "field": "ingredients", "note": "misread"}).json()["review_id"]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(rid, "asha")
    form = {"name": "Loose pack", "category": "7.2.1", "ingredients": "Wheat flour\nSugar"}
    with pytest.raises(ReviewError, match="barcode"):
        svc.approve(rid, "asha", form)
    out = svc.approve(rid, "asha", {**form, "barcode": gtin()})
    assert out["resolution"] == "published_new_version"


def test_the_no_barcode_button_is_easy_to_find():
    app_js = open(os.path.join(main.WEB_DIR, "app.js"), encoding="utf-8").read()
    start = app_js.index("async function scan()")
    body = app_js[start:app_js.index("\n}\n", start)]
    assert body.index("No barcode? Photograph the ingredients") < body.index("Take a photo of the barcode")
    assert 'Photograph the ingredients", () => { pending.barcode = null; go("photo"); }, "link")' not in body

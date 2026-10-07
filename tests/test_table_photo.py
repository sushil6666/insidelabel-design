"""
D-168 (Sushil, 2026-10-07): a published pack without a nutrition table offers, at the
end of its catalogue result, one photo of the table. The photo is read once (the same
single read as a scan); only the checked table is used (nutrition.check(), D-133), and
it waits for a reviewer as a `nutrition` item with the published content unchanged.
A photo that shows another barcode (D-143), or no usable table, adds nothing.
"""
import io
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_nutrition import GOLD, printed  # noqa: E402

from insidelabel import ratelimit, repro  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

INGREDIENTS = ["Refined wheat flour (Maida)", "Sugar", "Refined palm oil", "Milk solids", "Iodized salt"]
TABLE = GOLD["maliban-wafer-cheese"]["nutrition"]


def reading(ingredients=INGREDIENTS, table=None, **kw):
    v = {"front_status": "not_provided", "back_status": "read",
         "ingredients_status": "read" if ingredients else "not_found",
         "product": {"brand": "Testco", "name": "Cream Wafer", "variant": None, "net_quantity": None,
                     "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)] if ingredients else [],
         "ingredient_count": len(ingredients), "ingredients": ingredients, "allergen_statement": None,
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98 if ingredients else 0.0, "front_claims": 0.0, "product_identity": 0.8}}
    if table is not None:
        v["nutrition"] = table
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(fresh_db[0])
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield fresh_db[0]
    main.STORE, main.MEDIA = saved


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def photo():
    return b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes


def published(env):
    """A barcode whose pack is published without a nutrition table."""
    bc = gtin()
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")},
                                  data={"replay": reading(), "barcode": bc})
    assert r.status_code == 200, r.text
    item = q(env, """SELECT q.id FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s""", bc)[0][0]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(item, "sushil")
    svc.approve(item, "sushil", {"name": "Cream Wafer", "brand": "Testco", "category": "7.2.1",
                                 "ingredients": "\n".join(INGREDIENTS)})
    return bc


def lookup(bc):
    r = TestClient(main.app).post("/scan", data={"barcode": bc})
    assert r.status_code == 200, r.text
    return r.json()


def table_photo(bc, table=TABLE, ocr=None, data=None):
    data = data or photo()
    text = printed(table) if (ocr is None and table and table.get("rows")) else (ocr or "")
    with cloud_vision.replaying({cloud_vision.digest(data): text} if text else {}):
        return TestClient(main.app).post("/scan", files={"back": ("t.jpg", data, "image/jpeg")},
                                         data={"replay": reading([], table), "barcode": bc, "table_only": "true"})


def versions(env, bc):
    return q(env, """SELECT v.id, v.status, v.is_current, v.ingredient_lines, v.nutrition IS NOT NULL
                       FROM product_versions v JOIN products p ON p.id = v.product_id
                      WHERE p.barcode = %s ORDER BY v.version_no""", bc)


# ---------------------------------------------------------------- the offer

def test_a_published_pack_without_a_table_offers_one_photo(env):
    j = lookup(published(env))
    assert j["catalogue"]["table_wanted"] is True
    assert j["screen"]["table_offer"] == screen.TABLE_OFFER


def test_the_table_photo_waits_for_a_reviewer_and_changes_nothing_published(env):
    bc = published(env)
    before = versions(env, bc)
    findings = q(env, "SELECT count(*) FROM findings WHERE product_version_id = %s", before[0][0])[0][0]
    r = table_photo(bc)
    assert r.status_code == 200, r.text
    assert r.json()["table"] == {"status": "added", "text": screen.TABLE_ANSWER["added"], "kind": "done"}
    after = versions(env, bc)
    assert after[0] == before[0]                                       # the published version, untouched
    assert len(after) == 2
    vid, status, current, lines, has_table = after[1]
    assert (status, current, lines, has_table) == ("pending_review", False, before[0][3], True)
    assert q(env, "SELECT kind, status FROM review_queue WHERE product_version_id = %s", vid) == [("nutrition", "open")]
    assert q(env, "SELECT count(*) FROM findings WHERE product_version_id = %s", before[0][0])[0][0] == findings
    # Waiting now: no second offer, and a second photo isn't taken.
    assert "table_offer" not in lookup(bc)["screen"]
    again = table_photo(bc)
    assert again.status_code == 422 and again.json()["error"] == "table_not_wanted"


def test_a_pack_with_a_table_has_no_offer(env):
    bc = published(env)
    assert table_photo(bc).status_code == 200
    item = q(env, """SELECT q.id FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s AND q.kind = 'nutrition'""", bc)[0][0]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(item, "sushil")
    svc.approve(item, "sushil", {"name": "Cream Wafer", "brand": "Testco", "category": "7.2.1",
                                 "ingredients": "\n".join(INGREDIENTS), "nutrition_ok": "1"})
    j = lookup(bc)
    assert j["catalogue"]["table_wanted"] is False and "table_offer" not in j["screen"]


def test_no_table_or_an_unclear_one_adds_nothing(env):
    bc = published(env)
    none = table_photo(bc, table={"status": "not_found", "rows": []})   # the model's "no table" (prompt rule)
    assert none.status_code == 200
    assert none.json()["table"] == {"status": "no_table", "text": screen.TABLE_ANSWER["no_table"],
                                     "kind": "problem"}
    unclear = table_photo(bc, ocr="nothing here matches")             # the second reader finds no number
    assert unclear.json()["table"]["status"] == "unclear"
    assert unclear.json()["table"]["text"] == screen.TABLE_ANSWER["unclear"]
    assert unclear.json()["table"]["kind"] == "problem"                 # D-169
    assert len(versions(env, bc)) == 1
    rows = q(env, "SELECT outcome, error_code FROM scans WHERE id = %s", unclear.json()["scan_id"])
    assert rows == [("refused", "table_unclear")]                     # kept, with its trace (D-092)


def test_a_photo_of_another_barcode_adds_nothing(env):
    import zxingcpp
    from PIL import Image
    bc, other = published(env), gtin()
    img = Image.fromarray(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(other, zxingcpp.BarcodeFormat.EAN13),
                                                          scale=4))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    r = table_photo(bc, data=buf.getvalue())
    assert r.status_code == 200, r.text
    assert r.json()["table"] == {"status": "different_barcode",
                                  "text": screen.TABLE_ANSWER["different_barcode"], "kind": "problem"}
    assert len(versions(env, bc)) == 1


def test_a_table_photo_replays_to_the_same_answer(env):
    bc = published(env)
    first = table_photo(bc)
    with psycopg.connect(env) as c:
        cur = c.execute("SELECT * FROM scans WHERE id = %s", (first.json()["scan_id"],))
        row = dict(zip([d.name for d in cur.description], cur.fetchone()))
    assert row["request"]["table_only"] is True
    out = repro.replay_scan(row, media=main.MEDIA)
    assert out["status"] == 200 and out["body"]["table"]["status"] == "added"


def test_only_a_barcode_and_one_photo(env):
    bc = published(env)
    r = TestClient(main.app).post("/scan", files={"back": ("t.jpg", photo(), "image/jpeg"),
                                                  "front": ("f.jpg", photo(), "image/jpeg")},
                                  data={"replay": reading([], TABLE), "barcode": bc, "table_only": "true"})
    assert r.status_code == 422 and r.json()["error"] == "bad_table_photo"
    r = TestClient(main.app).post("/scan", files={"back": ("t.jpg", photo(), "image/jpeg")},
                                  data={"replay": reading([], TABLE), "table_only": "true"})
    assert r.status_code == 422 and r.json()["error"] == "bad_table_photo"


# ---------------------------------------------------------------- never offered here

CAT = {"source": "catalogue", "product_version_id": 1, "last_verified": "2026-10-01",
       "allergen_recheck_suggested": False, "front_wanted": False, "table_wanted": True}


def test_never_offered_from_a_screen_without_a_barcode_or_for_another_kind():
    from insidelabel.core import engine
    from insidelabel.reliability import gates
    verdict = engine.analyze("Sugar, Salt")
    rel = {"error": None, "caveats": [], "ingredients_complete": True, "verdict_safe_to_display": True}
    base = dict(verdict=verdict, display=gates.apply_display_rule(verdict, rel), claim_check=None,
                extracted={"ingredients": ["Sugar", "Salt"]}, reliability=rel, profiles=[],
                allergen_confidence=1.0, allergen_reliable=True,
                catalogue=CAT)
    assert screen.build(**base)["table_offer"] == screen.TABLE_OFFER                  # the food case
    assert "table_offer" not in screen.build(**{**base, "has_barcode": False})         # D-107
    assert "table_offer" not in screen.build(**{**base, "reliability": {**rel, "from_screen": True}})  # D-130
    assert "table_offer" not in screen.build(**{**base, "catalogue": {**CAT, "table_wanted": False}})
    infant = {"code": "infant", "evidence": [], "review": []}
    assert "table_offer" not in screen.build(**{**base, "kind": infant})                # D-140


def test_a_table_photo_counts_in_the_daily_photo_limit(monkeypatch):
    # D-095, D-148: the same budget as any photo scan. No store: the hit isn't looked up.
    monkeypatch.setattr(main, "STORE", None)
    monkeypatch.setattr(ratelimit.LIMITER, "rules", ratelimit.RULES)
    now = [2_000_000.0]
    monkeypatch.setattr(ratelimit.LIMITER, "clock", lambda: now[0])
    ratelimit.LIMITER.reset()
    device, bc = str(uuid.uuid4()), gtin()
    try:
        for i in range(ratelimit.PHOTO_SCANS_A_DAY):
            r = TestClient(main.app).post("/scan", files={"back": ("t.jpg", photo(), "image/jpeg")},
                                          data={"replay": reading([], TABLE), "barcode": bc, "table_only": "true",
                                                "device_id": device})
            assert r.status_code == 200, (i, r.text)
            now[0] += 60
        r = TestClient(main.app).post("/scan", files={"back": ("t.jpg", photo(), "image/jpeg")},
                                      data={"replay": reading([], TABLE), "barcode": bc, "table_only": "true",
                                            "device_id": device})
        assert r.status_code == 429
    finally:
        ratelimit.LIMITER.reset()


def test_review_shows_the_published_pack_beside_the_table_photo(env, monkeypatch):
    import base64

    from insidelabel.review import routes
    bc = published(env)
    assert table_photo(bc).status_code == 200
    item = q(env, """SELECT q.id FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s AND q.kind = 'nutrition'""", bc)[0][0]
    monkeypatch.setattr(routes, "SERVICE", ReviewService(env, main.ENGINE_VERSION))
    monkeypatch.setenv("INSIDELABEL_REVIEW_TOKEN", "table-token")
    with psycopg.connect(env) as c:
        if c.execute("SELECT count(*) FROM reviewers").fetchone()[0]:
            pytest.skip("reviewer accounts exist in this database; the shared token is refused")
    cred = base64.b64encode(b"asha:table-token").decode()
    page = TestClient(main.app, headers={"Authorization": f"Basic {cred}"}).get(f"/review/item/{item}")
    assert page.status_code == 200, page.text
    assert "Nutrition table photo" in page.text
    assert "Published version · back of pack" in page.text

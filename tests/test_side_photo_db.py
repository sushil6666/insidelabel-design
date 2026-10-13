"""
D-201 in the catalogue (migration 028): a side photo is its own scan row ('side',
'side_photo'), linked to the scan whose infant result it added to, kept for replay (D-092) and
shown on /review beside that scan. It never changes a catalogue version and never creates a
review item (Sushil, accepting D-201).
"""
import io
import json

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_pack_kind import reading, st  # noqa: E402
from test_pack_kind_db import env, item_page, post, q  # noqa: E402,F401

from insidelabel.api import main  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402

CEREAL = [st("Processed Cereal Based Complementary Food", "front"), st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"),
          st("IMPORTANT NOTICE"), st("Store in a cool and dry place in an air tight container")]
SIDE_TEXT = "Use only on the advice of a health worker. It is not the sole source of nourishment of an infant."


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


def test_migration_028_adds_the_parent_link_and_the_side_outcome(env):
    [(col,)] = q(env, """SELECT data_type FROM information_schema.columns
                          WHERE table_name = 'scans' AND column_name = 'parent_scan_id'""")
    assert col == "uuid"
    checks = dict(q(env, """SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                             WHERE conname IN ('scans_resolved_via_check', 'scans_outcome_check')"""))
    assert "'side'" in checks["scans_resolved_via_check"] and "'side_photo'" in checks["scans_outcome_check"]


def test_a_side_photo_is_its_own_scan_never_a_version_or_a_review_item(env, infant_on):
    j = post(gtin(), reading(["Rice flour", "Milk solids"], CEREAL, allergen="Contains milk."))
    vid, sid = j["catalogue"]["product_version_id"], j["scan_id"]
    notices = next(b for b in j["screen"]["infant"]["good"]["blocks"] if b["id"] == "notices")
    before = q(env, "SELECT (SELECT count(*) FROM product_versions), (SELECT count(*) FROM review_queue), "
                    "(SELECT count(*) FROM products)")
    [(raw_before,)] = q(env, "SELECT raw_extraction FROM product_versions WHERE id = %s", vid)
    photo = _jpeg()
    with cloud_vision.replaying({cloud_vision.digest(photo): SIDE_TEXT}):
        r = TestClient(main.app).post("/side-photo", files={"photo": ("s.jpg", photo, "image/jpeg")}, data={
            "found": json.dumps(notices["side"]["found"]), "missing": json.dumps(notices["side"]["missing"]),
            "photos": "2", "sides": "0", "scan_id": sid, "device_id": "dev-side-1", "photo_source": "camera"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert [f["id"] for f in got["found"]] == ["health_worker", "not_sole"] and got["scan_id"]
    # Nothing in the catalogue moved.
    assert q(env, "SELECT (SELECT count(*) FROM product_versions), (SELECT count(*) FROM review_queue), "
                  "(SELECT count(*) FROM products)") == before
    [(raw_after,)] = q(env, "SELECT raw_extraction FROM product_versions WHERE id = %s", vid)
    assert raw_after == raw_before
    # Its own row: linked to the scan, no version, no model cost, the text kept for replay.
    [(via, outcome, parent, version, cost, key, tr_ocr, req)] = q(
        env, """SELECT resolved_via, outcome, parent_scan_id, product_version_id, ai_cost_paise, back_image_key,
                       ocr, request FROM scans WHERE id = %s""", got["scan_id"])
    assert (via, outcome, str(parent), version, cost) == ("side", "side_photo", sid, None, 0)
    assert key and tr_ocr["side"]["reader"] == "cloud_vision" and tr_ocr["side"]["text"] == SIDE_TEXT
    assert tr_ocr["side"]["found"] == ["health_worker", "not_sole"]
    assert req["route"] == "side-photo" and req["parent_scan_id"] == sid
    assert "mothers_milk" in req["found"]                        # the server's own ids in the trace
    # /review shows it beside the scan.
    _item, _c, page = item_page(env, vid)
    assert "Side photo (D-201)" in page and "found: health_worker, not_sole" in page
    assert f"/review/media/{key}" in page


def test_an_unknown_parent_is_dropped_not_refused(env, infant_on):
    photo = _jpeg()
    with cloud_vision.replaying({cloud_vision.digest(photo): SIDE_TEXT}):
        r = TestClient(main.app).post("/side-photo", files={"photo": ("s.jpg", photo, "image/jpeg")}, data={
            "found": "[]", "missing": '["health_worker"]', "scan_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 200
    [(parent,)] = q(env, "SELECT parent_scan_id FROM scans WHERE id = %s", r.json()["scan_id"])
    assert parent is None

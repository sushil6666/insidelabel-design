"""
Where each photo came from (D-106): taken with the app's camera, or uploaded
(the gallery, a computer, dropped in). An AI-made or edited picture can only
arrive as an upload, so reviewers see uploads marked and look closer. The app
says which; the server records it on the scan and can't prove it.
"""
import base64
import io
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

c = TestClient(main.app)
TOKEN = "source-token-1"


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": "Source Biscuit", "variant": None, "net_quantity": None,
                     "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": ["Wheat flour, Sugar"], "ingredient_count": 2, "ingredients": ["Wheat flour", "Sugar"],
         "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    v.update(kw)
    return json.dumps(v)


def jpeg():
    b = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(b, "JPEG")
    return b.getvalue()


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def scan(**data):
    files = {"back": ("b.jpg", jpeg(), "image/jpeg")}
    return c.post("/scan", files=files, data={"replay": vision(product={"brand": "Testco",
                  "name": f"Source {uuid.uuid4().hex[:6]}", "variant": None, "net_quantity": None,
                  "veg_mark": None}), **data})


def reviewer():
    cred = base64.b64encode(f"asha:{TOKEN}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def test_the_scan_records_where_each_photo_came_from(env):
    r = scan(back_source="upload")
    assert r.status_code == 200
    s = row(env, "SELECT request FROM scans WHERE id = %s", r.json()["scan_id"])
    assert s["request"]["photo_sources"] == {"back": "upload"}


def test_an_unknown_source_is_refused(env):
    r = scan(back_source="telepathy")
    assert r.status_code == 422 and r.json()["error"] == "bad_photo_source"


def test_a_source_for_a_photo_not_sent_is_ignored(env):
    r = scan(back_source="camera", front_source="upload")
    s = row(env, "SELECT request FROM scans WHERE id = %s", r.json()["scan_id"])
    assert s["request"]["photo_sources"] == {"back": "camera"}


def _item_for(env, scan_id):
    return row(env, "SELECT id FROM review_queue WHERE scan_id = %s", scan_id)["id"]


def test_the_reviewer_sees_an_upload_marked(env):
    sid = scan(back_source="upload").json()["scan_id"]
    page = reviewer().get(f"/review/item/{_item_for(env, sid)}").text
    assert "Uploaded, not taken with the camera" in page
    assert re.search(r"AI|edited|screen", page)


def test_a_camera_photo_is_not_marked(env):
    sid = scan(back_source="camera").json()["scan_id"]
    page = reviewer().get(f"/review/item/{_item_for(env, sid)}").text
    assert "Uploaded, not taken with the camera" not in page
    assert "Taken with the app's camera" in page


def test_older_scans_say_nothing(env):
    sid = scan().json()["scan_id"]
    page = reviewer().get(f"/review/item/{_item_for(env, sid)}").text
    assert "Uploaded, not taken" not in page and "Taken with the app's camera" not in page


def test_the_queue_marks_items_with_an_upload(env):
    scan(back_source="upload")
    page = reviewer().get("/review").text
    assert "uploaded" in page.lower()


def test_the_app_sends_the_source():
    import os
    lib = open(os.path.join(main.WEB_DIR, "lib.js"), encoding="utf-8").read()
    assert '"back_source"' in lib and '"front_source"' in lib

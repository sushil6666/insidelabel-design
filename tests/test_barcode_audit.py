"""
Every published product's barcode against its own photos (tools/barcode_audit.py,
D-142). Product 42's case: published under the camera's 4901196008343, its back
photo reads 8901499008343. Real zxing-cpp reads of generated barcodes here.
"""
import json
import os
import sys

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel import barcode  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import ocr_check  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402
from test_check_photo import barcode_photo, label_photo  # noqa: E402
from test_review import TOKEN, approve, client, q, take_next, vision  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import barcode_audit  # noqa: E402

WRONG, RIGHT = "4901196008343", "8901499008343"


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    mp.setattr(ocr_check, "AVAILABLE", False)          # no Tesseract on generated photos: the OCR text is set below
    yield uri, main.MEDIA
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def publish(uri, code, photo, name, ocr=None):
    """A scan sent with `code` and a back photo, published by a reviewer; the product id."""
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                  data={"replay": vision(["Corn grits", "Salt"]), "barcode": code,
                                        "barcode_source": "camera"})
    assert r.status_code == 200, r.text
    if ocr:
        with psycopg.connect(uri) as c:
            c.execute("UPDATE scans SET ocr = %s WHERE id = %s",
                      (json.dumps({"back": {"reader": "cloud_vision", "text": ocr}}), r.json()["scan_id"]))
    c = client()
    approve(c, take_next(c), name=name, ingredients="Corn grits\nSalt", barcode=code)
    return q(uri, "SELECT id FROM products WHERE barcode = %s", code)[0][0]


def test_codes_are_found_in_ocr_text_as_printed_in_groups():
    text = "MRP Rs 45\n8 901499 008343\nFSSAI Lic. No. 10012011000123\nEAN:8901063093089"
    assert barcode.codes_in_text(text) == [RIGHT, "8901063093089"]
    assert barcode.codes_in_text("Best before 12 months") == []


def test_every_published_product_is_checked_against_its_own_photos(env):
    uri, media = env
    ids = {
        "misread": publish(uri, WRONG, barcode_photo(RIGHT), "Corn Flakes"),          # product 42's case
        "zxing": publish(uri, "8901063093089", barcode_photo("8901063093089"), "Oats"),
        "ocr": publish(uri, "8906002430017", label_photo(), "Poha", ocr="Net wt 500 g\n8 906002 430017"),
        "nothing": publish(uri, "8906002430031", label_photo(), "Rusk"),
    }
    rows = {r["id"]: r for r in barcode_audit.audit(barcode_audit.products(uri), media)}
    assert rows[ids["misread"]]["status"] == "MISMATCH" and rows[ids["misread"]]["zxing"] == [RIGHT]
    assert rows[ids["zxing"]]["status"] == "confirmed"
    assert rows[ids["ocr"]]["status"] == "confirmed" and rows[ids["ocr"]]["ocr"] == ["8906002430017"]
    assert rows[ids["nothing"]]["status"] == "unconfirmed"

    lines = []
    count = barcode_audit.report(list(rows.values()), out=lines.append)
    assert count == {"MISMATCH": 1, "confirmed": 2, "unconfirmed": 1}
    text = "\n".join(lines)
    assert f"barcode {WRONG}; scans sent {WRONG} (camera)" in text and f"zxing {RIGHT} on " in text
    assert "Oats" not in text                                   # confirmed ones only with --all


def test_deleted_photos_are_reported_not_guessed(env):
    uri, media = env
    pid = q(uri, "SELECT id FROM products WHERE name = 'Rusk'")[0][0]
    for (key,) in q(uri, """SELECT DISTINCT back_image_key FROM product_versions WHERE product_id = %s""", pid):
        media.delete(key)
    (row,) = [r for r in barcode_audit.audit(barcode_audit.products(uri), media) if r["id"] == pid]
    assert row["status"] == "no photos" and row["photos_gone"] == 1


def test_the_audit_writes_nothing(env):
    uri, media = env
    before = q(uri, "SELECT id, barcode FROM products ORDER BY id")
    barcode_audit.audit(barcode_audit.products(uri), media)
    assert q(uri, "SELECT id, barcode FROM products ORDER BY id") == before

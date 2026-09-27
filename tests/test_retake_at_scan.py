"""
D-118: a pack the scan would add to the catalogue, whose ingredient list Cloud
Vision can't confirm, gets one request for a clearer photo before the result.
"Use this one anyway" goes on. Packs already in the catalogue, scans without a
barcode, and scans where Cloud Vision didn't read the photo are never asked.

Review item 14 of the first shadow run is the case: Gemini read a list that
Cloud Vision's text of the same photo didn't contain at all. Cloud Vision's
text is replayed here (as repro.py does); nothing calls Google.
"""
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

INGREDIENTS = ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR", "REFINED PALM OIL", "MILK SOLIDS", "IODIZED SALT",
               "EMULSIFIER (322 (i))"]
CONFIRMS = ("INGREDIENTS: REFINED WHEAT FLOUR (MAIDA), SUGAR, REFINED PALM OIL, MILK SOLIDS, IODIZED SALT, "
            "EMULSIFIER (322 (i)). CONTAINS WHEAT, MILK. NUTRITION INFORMATION")
NO_LIST = "Best before 6 months from packaging. Net Weight 100 g. Store in a cool and dry place."


def vision():
    return json.dumps({
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Testco", "name": "Cream Biscuit", "variant": None, "net_quantity": None,
                    "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(INGREDIENTS)], "ingredient_count": len(INGREDIENTS),
        "ingredients": INGREDIENTS, "allergen_statement": "CONTAINS WHEAT, MILK.",
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


def scan(ocr_text, barcode="new", **data):
    """A back photo with its own bytes, Cloud Vision's text replayed for it (or none)."""
    photo = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    form = {"replay": vision(), **data}
    if barcode:
        form["barcode"] = gtin() if barcode == "new" else barcode
    texts = {cloud_vision.digest(photo): ocr_text} if ocr_text is not None else {}
    with cloud_vision.replaying(texts):
        r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")}, data=form)
    return r, form.get("barcode")


def queued(uri, barcode):
    return q(uri, """SELECT count(*) FROM review_queue q JOIN product_versions v ON v.id = q.product_version_id
                      JOIN products p ON p.id = v.product_id WHERE p.barcode = %s""", barcode)[0][0]


def test_a_new_pack_cloud_vision_cant_confirm_asks_for_a_clearer_photo(env):
    r, bc = scan(NO_LIST)
    assert r.status_code == 422, r.text
    s = r.json()["screen"]
    assert s["state"] == "retake" and s["can_use_anyway"] is True
    assert s["headline"]["text"] == "One clearer photo, please."
    assert "clearer photo of the ingredient list" in s["retake"]
    assert s["can_send"] is True                                        # two refusals still offer "Send it to us"
    # Traced like any refusal (D-092), and nothing added to the catalogue yet.
    row = q(env, "SELECT outcome, error_code FROM scans WHERE id = %s", r.json()["scan_id"])
    assert row == [("refused", "independent_read_failed")]
    assert queued(env, bc) == 0


def test_use_this_one_anyway_gives_the_result_and_queues_the_pack(env):
    r, bc = scan(NO_LIST)
    assert r.status_code == 422
    r2, _ = scan(NO_LIST, barcode=bc, accept_unconfirmed="true")
    assert r2.status_code == 200, r2.text
    assert r2.json()["screen"]["state"] == "result"
    assert queued(env, bc) == 1
    trace = q(env, "SELECT request FROM scans WHERE id = %s", r2.json()["scan_id"])[0][0]
    assert trace["accept_unconfirmed"] is True                          # the review agents can see it


def test_a_list_cloud_vision_confirms_goes_straight_to_the_result(env):
    r, bc = scan(CONFIRMS)
    assert r.status_code == 200, r.text
    assert queued(env, bc) == 1


def test_a_pack_already_in_the_catalogue_is_never_asked(env):
    r, bc = scan(CONFIRMS)
    item = q(env, "SELECT id FROM review_queue ORDER BY id DESC LIMIT 1")[0][0]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(item, "sushil")
    svc.approve(item, "sushil", {"name": "Cream Biscuit", "brand": "Testco", "category": "7.2.1",
                                 "ingredients": "\n".join(INGREDIENTS)})
    r2, _ = scan(NO_LIST, barcode=bc)                                   # the same label, badly photographed
    assert r2.status_code == 200, r2.text


def test_no_barcode_or_no_cloud_vision_read_is_never_asked(env):
    r, _ = scan(NO_LIST, barcode=None)                                  # D-107: not catalogued anyway
    assert r.status_code == 200, r.text
    r2, _ = scan(None)                                                  # the Tesseract fallback: nothing independent
    assert r2.status_code == 200, r2.text

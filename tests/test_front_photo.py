"""
The front photo, once per pack (D-100).

The front carries the brand's claims and the product's name as sold, so the
catalogue wants one for every version, but a user shouldn't be asked for it
on every scan. These tests pin: the catalogue says when a front is wanted; a
front sent alone costs no model call and goes to a reviewer; it is queued once
per version; and a reviewer's approval records it (with or without claims), so
the app stops asking.
"""
import base64
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

TOKEN = "test-token-front"
def _jpeg():
    """A real, readable-sized photo, different every run (D-103 checks the file)."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


# The back only travels with a recorded answer (no file check; OCR reads it, so
# it stays tiny). The front also goes alone, down the no-model path, which checks it.
BACK_JPEG = b"\xff\xd8\xff\xe0back" + uuid.uuid4().bytes
FRONT_JPEG = _jpeg()
INGREDIENTS = ["Whole wheat flour", "Sugar", "Groundnut oil", "Salt"]


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": "Atta Cookie", "variant": None,
                     "net_quantity": None, "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(INGREDIENTS)], "ingredient_count": len(INGREDIENTS),
         "ingredients": INGREDIENTS, "allergen_statement": "Contains wheat, peanut.",
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}}
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = routes.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    routes.SERVICE = ReviewService(uri, main.ENGINE_VERSION)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_REVIEW_TOKEN", TOKEN)
    mp.delenv("GOOGLE_VISION_KEY", raising=False)        # fake photos: never call Google
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def reviewer():
    cred = base64.b64encode(f"asha:{TOKEN}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def csrf(page_html):
    return re.search(r'name="csrf" value="([0-9a-f]+)"', page_html).group(1)


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def post(**data):
    files = {}
    if data.pop("back", False):
        files["back"] = ("b.jpg", BACK_JPEG, "image/jpeg")
    if data.pop("front", False):
        files["front"] = ("f.jpg", FRONT_JPEG, "image/jpeg")
    return TestClient(main.app).post("/scan", files=files or None, data=data)


def approve(item_id, **fields):
    c = reviewer()
    page = c.get(f"/review/item/{item_id}").text
    form = {"csrf": csrf(page), "name": "Atta Cookie", "brand": "Testco", "variant": "", "barcode": "",
            "ingredients": "\n".join(INGREDIENTS), "allergen_statement": "Contains wheat, peanut.",
            "front_claims": "", "note": "", "category": "7.2.1"}
    form.update(fields)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": form["csrf"]})
    r = c.post(f"/review/item/{item_id}/approve", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text
    return page


def published(uri, barcode):
    """Scan the back, then publish it through the reviewer screen. Returns the version id."""
    j = post(back=True, barcode=barcode, replay=vision()).json()
    item = q(uri, "SELECT id FROM review_queue WHERE product_version_id = %s AND kind = 'new_product'",
             j["catalogue"]["product_version_id"])[0][0]
    approve(item)
    return post(barcode=barcode).json()["catalogue"]["product_version_id"]


def front_items(uri, vid):
    return q(uri, "SELECT id, scan_id, status FROM review_queue WHERE kind = 'front_photo' "
                  "AND product_version_id = %s", vid)


def test_the_front_is_asked_for_once_and_recorded(env):
    bc = "8900000009909"
    vid = published(env, bc)
    assert post(barcode=bc).json()["catalogue"]["front_wanted"] is True

    dev = str(uuid.uuid4())
    j = post(barcode=bc, front=True, device_id=dev).json()
    # Still the reviewed record, straight away, and no model was asked.
    assert j["catalogue"]["source"] == "catalogue" and j["catalogue"]["product_version_id"] == vid
    assert j["catalogue"]["front_received"] is True and j["catalogue"]["front_wanted"] is False
    assert next(iter(j)) == "allergens"
    row = q(env, "SELECT cache_hit, ai_cost_paise, front_image_key IS NOT NULL FROM scans WHERE id = %s",
            j["scan_id"])[0]
    assert row == (True, 0, True)
    items = front_items(env, vid)
    assert len(items) == 1 and str(items[0][1]) == j["scan_id"]

    # Waiting for review: nobody else is asked, and a second photo isn't queued twice.
    assert post(barcode=bc).json()["catalogue"]["front_wanted"] is False
    post(barcode=bc, front=True)
    assert len(front_items(env, vid)) == 1

    # The reviewer sees the back on file and the new front, and types the claims.
    page = approve(items[0][0], front_claims="No maida\nBaked, not fried")
    assert "Front of pack for a published product" in page
    assert page.count("/review/media/") >= 4                     # two photos, each linked twice
    after = post(barcode=bc).json()
    new_vid = after["catalogue"]["product_version_id"]
    assert new_vid != vid and after["catalogue"]["front_wanted"] is False
    claims, has_front = q(env, "SELECT front_claims, front_image_key IS NOT NULL FROM product_versions "
                               "WHERE id = %s", new_vid)[0]
    assert claims == ["No maida", "Baked, not fried"] and has_front

    # The person who sent it is thanked when they next open the app.
    ups = TestClient(main.app).get("/updates", params={"device_id": dev}).json()["updates"]
    assert [(u["kind"], u["ready"]) for u in ups] == [("front_photo", True)]


def test_a_front_with_no_claims_still_counts(env):
    bc = "8900000009916"
    vid = published(env, bc)
    post(barcode=bc, front=True)
    approve(front_items(env, vid)[0][0], front_claims="")
    after = post(barcode=bc).json()["catalogue"]
    assert after["product_version_id"] != vid and after["front_wanted"] is False


def test_a_front_alone_needs_the_pack_in_the_catalogue(env, monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("the model must not be called for a front photo alone")
    monkeypatch.setattr(main.gemini, "analyze_images", no_model)
    r = post(barcode="8900000009923", front=True)
    assert r.status_code == 422 and r.json()["error"] == "back_required"


def test_a_recheck_with_the_front_queues_it(env):
    bc = "8900000009930"
    vid = published(env, bc)
    j = post(back=True, front=True, barcode=bc, pairing_confirmed="true",
             replay=vision(front_status="read", front_claims=["No palm oil"],
                           product_match={"status": "indeterminate", "evidence": []})).json()
    assert j["catalogue"]["status"] == "published" and j["catalogue"]["queued_for_review"] == "front_photo"
    assert len(front_items(env, vid)) == 1
    # Without a confirmed pairing the front may be another pack's: not queued.
    bc2 = "8900000009947"
    vid2 = published(env, bc2)
    j2 = post(back=True, front=True, barcode=bc2,
              replay=vision(front_status="read", product_match={"status": "indeterminate", "evidence": []})).json()
    assert j2["catalogue"]["queued_for_review"] is None and front_items(env, vid2) == []

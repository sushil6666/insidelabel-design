"""
D-119: a long ingredient list in two or three photos, joined on the server into
one back photo. One part is today's scan, unchanged. Asked for by Sushil in the
shop (Britannia 50-50 Cheeze Dipped: the list doesn't fit one photo).
"""
import io
import json

import pytest
from PIL import Image

from insidelabel import photo_join


def jpeg(w, h, colour=(255, 255, 255)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, "JPEG")
    return buf.getvalue()


def label_like(w, h):
    """A photo the D-103 checks accept: dark lines of 'text' on a light pack."""
    from PIL import ImageDraw
    im = Image.new("RGB", (w, h), (235, 225, 200))
    d = ImageDraw.Draw(im)
    for y in range(20, h - 20, 28):
        d.rectangle([30, y, w - 60 - (y * 7) % 200, y + 12], fill=(30, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def size(data):
    return Image.open(io.BytesIO(data)).size


def test_two_parts_become_one_tall_photo_in_order():
    top, bottom = jpeg(1200, 900, (255, 0, 0)), jpeg(1200, 700, (0, 0, 255))
    data, mime = photo_join.join([(top, "image/jpeg"), (bottom, "image/jpeg")])
    assert mime == "image/jpeg"
    assert size(data) == (1200, 900 + photo_join.GAP + 700)
    im = Image.open(io.BytesIO(data))
    assert im.getpixel((600, 100))[0] > 200 and im.getpixel((600, 100))[2] < 60     # part 1 on top
    assert im.getpixel((600, 1500))[2] > 200 and im.getpixel((600, 1500))[0] < 60   # part 2 below


def test_parts_are_scaled_to_one_width_so_the_text_keeps_its_size():
    data, _ = photo_join.join([(jpeg(1600, 800), "image/jpeg"), (jpeg(800, 400), "image/jpeg")])
    assert size(data) == (1600, 800 + photo_join.GAP + 800)


def test_three_tall_parts_are_shrunk_to_the_limit():
    data, _ = photo_join.join([(jpeg(1600, 2000), "image/jpeg")] * 3)
    assert max(size(data)) == photo_join.MAX_SIDE


def test_only_two_or_three_parts_and_readable_ones():
    with pytest.raises(photo_join.JoinError):
        photo_join.join([(jpeg(100, 100), "image/jpeg")])
    with pytest.raises(photo_join.JoinError):
        photo_join.join([(jpeg(100, 100), "image/jpeg")] * 4)
    with pytest.raises(photo_join.JoinError):
        photo_join.join([(jpeg(100, 100), "image/jpeg"), (b"not an image", "image/heic")])


# ---------------------------------------------------------------- through /scan

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402

ING = ["Refined Wheat Flour (Maida)", "Sugar", "Cheese Powder (3%)", "Iodised Salt"]


def vision():
    return json.dumps({
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Testco", "name": "Cheese Dipped", "variant": None, "net_quantity": None,
                    "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ING)], "ingredient_count": len(ING), "ingredients": ING,
        "allergen_statement": "Contains wheat, milk.", "front_claims": [], "front_claim_footnotes": [],
        "extraction_notes": [], "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}})


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    uri = fresh_db[0]
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(uri)
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield uri
    main.STORE, main.MEDIA = saved


def post(files, **data):
    return TestClient(main.app).post("/scan", files=files, data={"replay": vision(), "barcode": gtin(), **data})


def stored_back(uri, scan_id):
    with psycopg.connect(uri) as c:
        key, request = c.execute("SELECT back_image_key, request FROM scans WHERE id = %s", (scan_id,)).fetchone()
    return main.MEDIA.get(key)[0], request


def test_a_list_in_two_parts_is_stored_as_one_back_photo(env):
    r = post({"back": ("b.jpg", jpeg(1000, 800), "image/jpeg"), "back2": ("b2.jpg", jpeg(1000, 600), "image/jpeg")},
             back_source="camera", back2_source="camera")
    assert r.status_code == 200, r.text
    data, request = stored_back(env, r.json()["scan_id"])
    assert size(data) == (1000, 800 + photo_join.GAP + 600)
    assert request["back_parts"] == 2 and request["images"] == ["back"]
    assert request["photo_sources"] == {"back": "camera", "back2": "camera"}   # D-106 kept per part


def test_one_part_is_todays_scan_unchanged(env):
    photo = jpeg(1000, 800)
    r = post({"back": ("b.jpg", photo, "image/jpeg")})
    assert r.status_code == 200, r.text
    data, request = stored_back(env, r.json()["scan_id"])
    assert data == photo and request["back_parts"] == 1


def test_parts_must_come_in_order(env):
    r = post({"back2": ("b2.jpg", jpeg(1000, 600), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == "parts_out_of_order"
    r = post({"back": ("b.jpg", jpeg(1000, 800), "image/jpeg"), "back3": ("b3.jpg", jpeg(1000, 600), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == "parts_out_of_order"


def test_each_part_is_checked_on_its_own():
    # D-103 runs before the join; replayed answers skip it, so this one sends no replay.
    r = TestClient(main.app).post("/scan", data={"barcode": gtin()}, files={
        "back": ("b.jpg", label_like(1000, 800), "image/jpeg"),
        "back2": ("b2.jpg", jpeg(40, 40), "image/jpeg")})
    assert r.status_code == 422, r.text
    assert r.json()["role"] == "back2"
    assert "part 2" in r.json()["detail"]

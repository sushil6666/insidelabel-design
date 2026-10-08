"""
The pack picture (D-182): a real photo of a pack's front on every result for its barcode.

Sushil, 2026-10-08: "Own photos", then "Shoppers too". These tests pin who can make one
(a person on /review, never the review agent), whose photo can be used (a shopper's only
under the terms that say so, from 2026-10-08), what is kept (a small copy without
metadata, under its own key) and what is served (only pictures being shown).
"""
import io
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from insidelabel import pictures  # noqa: E402
from insidelabel.api import main  # noqa: E402
from tests.test_front_photo import (  # noqa: E402,F401 - the same catalogue set-up
    approve, csrf, env, post, published, q, reviewer)


def _photo(size=(1200, 1600), exif=True):
    buf = io.BytesIO()
    im = Image.effect_noise(size, 60).convert("RGB")
    if exif:
        ex = Image.Exif()
        ex[0x0110] = "PhoneModel X"                       # Model
        ex[0x0132] = "2026:10:08 09:00:00"                # DateTime
        im.save(buf, "JPEG", exif=ex.tobytes())
    else:
        im.save(buf, "JPEG")
    return buf.getvalue()


def agreed(uri, version):
    dev = str(uuid.uuid4())
    with psycopg.connect(uri) as c:
        c.execute("INSERT INTO users (id) VALUES (%s)", (dev,))
        c.execute("INSERT INTO agreements (user_id, terms_version) VALUES (%s, %s)", (dev, version))
    return dev


def send_front(uri, barcode, device, data):
    files = {"front": ("f.jpg", data, "image/jpeg")}
    j = TestClient(main.app).post("/scan", files=files, data={"barcode": barcode, "device_id": device}).json()
    return q(uri, "SELECT id FROM review_queue WHERE kind = 'front_photo' AND scan_id = %s", j["scan_id"])[0][0]


def test_the_terms_that_allow_it_are_the_current_ones():
    assert main.TERMS["version"] == pictures.TERMS_FROM == "2026-10-08"
    text = " ".join(main.TERMS["points"])
    assert "shown to other InsideLabel users as that product's picture" in text
    assert [x["kind"] for x in main.TERMS["examples"]["items"]] == ["front", "list", "table"]
    assert "suggestion" in main.TERMS["examples"]["note"]


def test_shrink_keeps_a_small_copy_without_metadata():
    small = pictures.shrink(_photo())
    im = Image.open(io.BytesIO(small))
    assert im.format == "JPEG" and max(im.size) == pictures.LONG_EDGE and im.size == (360, 480)
    assert not im.getexif() and "exif" not in im.info
    with pytest.raises(pictures.PictureError):
        pictures.shrink(b"not a photo")


def test_a_shoppers_front_becomes_the_pack_picture_when_a_person_ticks_it(env):
    bc = "8900000019908"
    vid = published(env, bc)
    assert "pack_picture" not in post(barcode=bc).json()["screen"]
    item = send_front(env, bc, agreed(env, "2026-10-08"), _photo())
    page = reviewer().get(f"/review/item/{item}").text
    assert "Show this front photo to everyone who scans this barcode" in page

    # Ticked without the second box: refused, nothing published.
    c = reviewer()
    c.post(f"/review/item/{item}/claim", data={"csrf": csrf(page)})
    form = {"csrf": csrf(page), "name": "Atta Cookie", "brand": "Testco", "variant": "", "barcode": "",
            "ingredients": "Whole wheat flour\nSugar\nGroundnut oil\nSalt", "allergen_statement": "Contains wheat, peanut.",
            "front_claims": "", "note": "", "category": "7.2.1", "pack_picture": "1"}
    r = c.post(f"/review/item/{item}/approve", data=form, follow_redirects=False)
    assert "pack+alone" in r.headers["location"] or "pack%20alone" in r.headers["location"]
    assert q(env, "SELECT count(*) FROM pack_pictures")[0][0] == 0

    r = c.post(f"/review/item/{item}/approve", data=form | {"pack_alone": "1"}, follow_redirects=False)
    assert r.headers["location"] == "/review"
    (key, source, by, scan_id), = q(env, "SELECT image_key, source, approved_by, scan_id FROM pack_pictures")
    assert source == "shopper_photo" and by == "asha" and scan_id is not None

    # Every result for the barcode carries it, worded by the server; the copy is served publicly.
    screen = post(barcode=bc).json()["screen"]
    pic = screen["pack_picture"]
    assert pic["url"] == f"/pack-picture/{key}" and pic["alt"] == "Photo of the front of the pack"
    assert re.fullmatch(r"Photo of the pack, checked by our team on \d{1,2} [A-Z][a-z]{2} \d{4}", pic["caption"])
    got = TestClient(main.app).get(pic["url"])
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert "public" in got.headers["cache-control"]
    assert max(Image.open(io.BytesIO(got.content)).size) <= pictures.LONG_EDGE
    # Its own key: the shopper's photo still goes at 30 days, and stays private.
    front_key = q(env, "SELECT front_image_key FROM scans WHERE id = %s", scan_id)[0][0]
    assert front_key != key
    assert TestClient(main.app).get(f"/pack-picture/{front_key}").status_code == 404
    assert vid


def test_a_front_sent_under_older_terms_is_never_offered(env):
    bc = "8900000019915"
    published(env, bc)
    item = send_front(env, bc, agreed(env, "2026-09-26"), _photo())
    page = reviewer().get(f"/review/item/{item}").text
    assert "can&#39;t be shown" in page or "can't be shown" in page
    assert 'name="pack_picture"' not in page


def test_the_review_agent_never_makes_one(env):
    bc = "8900000019922"
    published(env, bc)
    before = q(env, "SELECT count(*) FROM pack_pictures")[0][0]
    item = send_front(env, bc, agreed(env, "2026-10-08"), _photo())
    # The agent publishes through ReviewService.approve(), which never makes a picture: only
    # the /review route does, for a person who ticked both boxes.
    from insidelabel.review import routes
    routes.SERVICE.claim(item, "agent")
    routes.SERVICE.approve(item, "agent", {"ingredients": "Whole wheat flour\nSugar\nGroundnut oil\nSalt",
                                           "allergen_statement": "Contains wheat, peanut.", "name": "Atta Cookie",
                                           "category": "7.2.1", "pack_picture": "1", "pack_alone": "1"})
    assert q(env, "SELECT status FROM review_queue WHERE id = %s", item)[0][0] == "done"
    assert q(env, "SELECT count(*) FROM pack_pictures")[0][0] == before


def test_a_reviewer_uploads_one_and_can_remove_it(env):
    bc = "8900000019939"
    published(env, bc)
    c = reviewer()
    page = c.get("/review/pictures").text
    assert "Show this picture" in page
    form = {"csrf": csrf(page), "barcode": bc}
    files = {"photo": ("p.jpg", _photo(exif=False), "image/jpeg")}
    r = c.post("/review/pictures", data=form, files=files, follow_redirects=False)
    assert "Tick+both+boxes" in r.headers["location"] or "Tick%20both%20boxes" in r.headers["location"]
    r = c.post("/review/pictures", data=form | {"pack_alone": "1", "same_product": "1"}, files=files,
               follow_redirects=False)
    assert r.headers["location"] == f"/review/pictures?done={bc}"
    pic = post(barcode=bc).json()["screen"]["pack_picture"]
    assert TestClient(main.app).get(pic["url"]).status_code == 200

    # Not a catalogue barcode: refused.
    r = c.post("/review/pictures", data=form | {"barcode": "8901088072236", "pack_alone": "1", "same_product": "1"},
               files=files, follow_redirects=False)
    assert "No+product" in r.headers["location"] or "No%20product" in r.headers["location"]

    pid = q(env, "SELECT pp.id FROM pack_pictures pp JOIN products p ON p.id = pp.product_id WHERE p.barcode = %s", bc)[0][0]
    page = c.get("/review/pictures").text
    c.post(f"/review/pictures/{pid}/remove", data={"csrf": csrf(page)})
    assert "pack_picture" not in post(barcode=bc).json()["screen"]
    assert TestClient(main.app).get(pic["url"]).status_code == 404
    assert q(env, "SELECT removed_by FROM pack_pictures WHERE id = %s", pid)[0][0] == "asha"


def test_the_public_route_refuses_anything_else(env):
    assert TestClient(main.app).get("/pack-picture/../secret").status_code == 404
    assert TestClient(main.app).get("/pack-picture/" + "0" * 64 + ".jpg").status_code == 404

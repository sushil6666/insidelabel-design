"""
D-167 (Sushil, 2026-10-07): a result for a barcode we haven't checked yet says so,
on the first scan and on every scan before review. Review item 66: a tester used
"Report a mistake" to ask why the review screen came up. Never without a barcode
(D-107), from a screen (D-130), for a pack that isn't food, for a refusal, or for a
catalogue hit with a checked version.
"""
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.lenses import screen  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

INGREDIENTS = ["Refined wheat flour (Maida)", "Sugar", "Refined palm oil", "Milk solids", "Iodized salt"]


def reading(ingredients=INGREDIENTS, **kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": "Cream Biscuit", "variant": None, "net_quantity": None,
                     "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
         "ingredients": ingredients, "allergen_statement": "Contains wheat, milk.",
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}}
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(fresh_db[0])
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield fresh_db[0]
    main.STORE, main.MEDIA = saved


def scan(barcode=None, photo=True, **kw):
    data = {"replay": reading(**kw)} if photo else {}
    if barcode:
        data["barcode"] = barcode
    files = {"back": ("b.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes, "image/jpeg")} if photo else None
    return TestClient(main.app).post("/scan", files=files, data=data)


def note(r):
    return (r.json().get("screen") or {}).get("catalogue_note")


def test_the_first_and_second_scan_before_review_say_we_havent_checked_it(env):
    bc = gtin()
    first = scan(bc)
    assert first.status_code == 200, first.text
    assert first.json()["catalogue"]["queued_for_review"] == "new_product"
    assert note(first) == screen.UNCHECKED_NOTE
    second = scan(bc)                                                # the same pack, before review
    assert second.status_code == 200, second.text
    assert second.json()["catalogue"]["status"] == "pending_review"
    assert note(second) == screen.UNCHECKED_NOTE


def test_a_checked_pack_has_no_note(env):
    bc = gtin()
    assert scan(bc).status_code == 200
    with psycopg.connect(env) as c:
        item = c.execute("SELECT id FROM review_queue ORDER BY id DESC LIMIT 1").fetchone()[0]
    svc = ReviewService(env, main.ENGINE_VERSION)
    assert svc.claim(item, "sushil")
    svc.approve(item, "sushil", {"name": "Cream Biscuit", "brand": "Testco", "category": "7.2.1",
                                 "ingredients": "\n".join(INGREDIENTS)})
    hit = scan(bc, photo=False)                                      # a catalogue hit
    assert hit.status_code == 200, hit.text
    assert note(hit) is None
    again = scan(bc)                                                 # the same label, re-read
    assert again.status_code == 200 and note(again) is None
    changed = scan(bc, ingredients=INGREDIENTS + ["Emulsifier (322)"])   # a reformulation: checked before
    assert changed.status_code == 200, changed.text
    assert changed.json()["catalogue"]["status"] == "pending_review"
    assert note(changed) is None


def test_no_barcode_a_screen_a_refusal_or_not_food_get_no_unchecked_note(env):
    assert note(scan()) == screen.UNLISTED_NOTE                       # D-107
    from_screen = scan(gtin(), image_content={"back": "screen"})      # D-130
    assert from_screen.status_code == 200, from_screen.text
    assert note(from_screen) == screen.SCREEN_NOTE
    refused = scan(gtin(), back_status="unreadable")
    assert refused.status_code == 422 and note(refused) is None
    supplement = scan(gtin(), pack_statements=[{"text": "HEALTH SUPPLEMENT", "face": "back"},
                                               {"text": "NOT FOR MEDICINAL USE", "face": "back"}],
                      licences=[{"text": "FSSAI Lic. No. 10012345678901", "face": "back"}])
    assert supplement.status_code == 200, supplement.text
    assert supplement.json()["pack_kind"]["code"] == "supplement"
    assert note(supplement) is None

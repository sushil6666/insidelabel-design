"""
D-133 in the catalogue: the checked nutrition table is stored on the version a
scan creates, a reviewer confirms it against the photo on /review, and only a
confirmed table is published and served from the barcode. A pack published
before D-133 gets its table through a new version, reviewed as kind 'nutrition'.
The review checker (D-117) sends an item to a person when a table number isn't
in Cloud Vision's text.
"""
import base64
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import cloud_vision  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import checker, routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

TOKEN = "test-token-nutrition"
INGREDIENTS = ["Whole wheat flour", "Sugar", "Groundnut oil", "Salt"]
TABLE = {"status": "read", "per_100_basis": "Per 100 g", "rda_column": "% RDA per serve", "serving_size": "25 g",
         "servings_per_pack": "4", "rows": [
             {"nutrient": "Energy", "unit": None, "per_100": "480 kcal", "per_serving": None, "rda_percent": "6"},
             {"nutrient": "Added sugars", "unit": None, "per_100": "18 g", "per_serving": None, "rda_percent": "9"},
             {"nutrient": "Sodium", "unit": None, "per_100": "320 mg", "per_serving": None, "rda_percent": "4"}]}
TEXT = ("INGREDIENTS: Whole wheat flour, Sugar, Groundnut oil, Salt. Contains wheat, peanut. "
        "Nutrition information Per 100 g % RDA per serve Serving size 25 g, 4 servings "
        "Energy 480 kcal 6 Added sugars 18 g 9 Sodium 320 mg 4")


def vision(table=None):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": "Atta Cookie", "variant": None, "net_quantity": "100 g",
                     "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(INGREDIENTS)], "ingredient_count": len(INGREDIENTS),
         "ingredients": INGREDIENTS, "allergen_statement": "Contains wheat, peanut.",
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}}
    if table is not None:
        v["nutrition"] = table
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
    mp.delenv("GOOGLE_VISION_KEY", raising=False)
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def reviewer():
    cred = base64.b64encode(f"asha:{TOKEN}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def post(barcode, table=None):
    photo = b"\xff\xd8\xff\xe0back" + uuid.uuid4().bytes
    with cloud_vision.replaying({cloud_vision.digest(photo): TEXT}):
        return TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                         data={"barcode": barcode, "replay": vision(table)})


def lookup(barcode):
    return TestClient(main.app).post("/scan", data={"barcode": barcode}).json()


def approve(item_id, refused=False, **fields):
    c = reviewer()
    page = c.get(f"/review/item/{item_id}").text
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    form = {"csrf": token, "name": "Atta Cookie", "brand": "Testco", "variant": "", "barcode": "",
            "ingredients": "\n".join(INGREDIENTS), "allergen_statement": "Contains wheat, peanut.",
            "front_claims": "", "note": "", "category": "7.2.1"}
    form.update(fields)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": token})
    r = c.post(f"/review/item/{item_id}/approve", data=form, follow_redirects=False)
    # Published: back to the queue. Refused: back to the item, with the reason.
    assert r.status_code == 303 and ("error=" in r.headers["location"]) == refused, r.headers.get("location")
    return page


def item_for(uri, vid, kind):
    return q(uri, "SELECT id FROM review_queue WHERE product_version_id = %s AND kind = %s", vid, kind)[0][0]


def test_a_new_pack_keeps_its_table_for_the_reviewer_and_publishes_it_once_confirmed(env):
    bc = gtin()
    j = post(bc, TABLE).json()
    assert j["nutrition"]["status"] == "read" and set(j["nutrition"]["values"]) == {"energy", "added_sugars", "sodium"}
    vid = j["catalogue"]["product_version_id"]
    [(stored,)] = q(env, "SELECT nutrition FROM product_versions WHERE id = %s", vid)
    assert stored["values"]["added_sugars"]["printed"] == "18"
    page = approve(item_for(env, vid, "new_product"), nutrition_ok="1")
    assert "Every number shown to users matches the photo" in page and "Added sugars" in page
    [(published,)] = q(env, "SELECT nutrition FROM product_versions WHERE id = %s", vid)
    assert published["confirmed_by"] == "asha"
    hit = lookup(bc)
    assert hit["catalogue"]["source"] == "catalogue" and hit["nutrition"]["values"]["sodium"]["value"] == 320
    rows = {r["key"]: r for r in hit["screen"]["nutrition"]["rows"]}
    assert rows["added_sugars"]["text"] == "Added sugar: 18 g per 100 g. ICMR-NIN counts more than 3 g per 100 g as high."
    assert hit["screen"]["nutrition"]["ask_photo"] is False


def test_an_unconfirmed_table_is_published_without_it(env):
    bc = gtin()
    vid = post(bc, TABLE).json()["catalogue"]["product_version_id"]
    approve(item_for(env, vid, "new_product"))
    assert q(env, "SELECT nutrition FROM product_versions WHERE id = %s", vid) == [(None,)]
    hit = lookup(bc)
    assert hit["nutrition"] is None and "nutrition" not in hit["screen"]


def test_a_published_pack_gets_its_table_through_review(env):
    bc = gtin()
    vid = post(bc).json()["catalogue"]["product_version_id"]          # read before D-133: no table
    approve(item_for(env, vid, "new_product"))
    j = post(bc, TABLE).json()                                         # a later scan reads the table
    v2 = j["catalogue"]["product_version_id"]
    assert v2 != vid and j["catalogue"]["queued_for_review"] == "nutrition"
    assert lookup(bc)["nutrition"] is None                             # not shown until confirmed
    item = item_for(env, v2, "nutrition")
    approve(item, refused=True)                                        # no tick: refused, stays open
    assert q(env, "SELECT status FROM review_queue WHERE id = %s", item) == [("claimed",)]
    approve(item, nutrition_ok="1")
    hit = lookup(bc)
    assert hit["catalogue"]["product_version_id"] == v2 and hit["nutrition"]["values"]["energy"]["value"] == 480
    # The same scan again: nothing new to review.
    again = post(bc, TABLE).json()
    assert again["catalogue"]["product_version_id"] == v2 and again["catalogue"]["queued_for_review"] is None


def test_a_waiting_version_gets_the_table_from_a_later_scan(env):
    bc = gtin()
    vid = post(bc).json()["catalogue"]["product_version_id"]
    assert post(bc, TABLE).json()["catalogue"]["product_version_id"] == vid
    [(stored,)] = q(env, "SELECT nutrition FROM product_versions WHERE id = %s", vid)
    assert stored["status"] == "read"


def test_the_checker_sends_a_number_it_cant_find_to_a_person():
    panel = {"status": "read", "values": {"energy": {"value": 480.0, "unit": "kcal", "printed": "480", "bound": None},
                                          "sodium": {"value": 320.0, "unit": "mg", "printed": "320", "bound": None}},
             "serving": {"value": 25.0, "unit": "g", "printed": "25"}}
    draft = {"ingredients": INGREDIENTS, "name": "Atta Cookie", "category": "7.2.1"}

    def result(ctx):
        return next(x for x in checker.check(draft, ctx) if x["check"] == "nutrition_in_ocr")
    assert result({"ocr_text": TEXT, "nutrition": panel})["ok"]
    bad = result({"ocr_text": TEXT.replace("320", "3 20"), "nutrition": panel})
    assert not bad["ok"] and "Sodium 320" in bad["detail"]
    assert result({"ocr_text": TEXT, "nutrition": None})["ok"]        # no table, nothing to check

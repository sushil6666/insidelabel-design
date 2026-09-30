"""
D-139, D-140 in the catalogue (migration 019): the version a scan creates keeps
the kind and its printed evidence; /review shows them, and for a pack that isn't
food offers D-116's reason; a published supplement is served from its barcode
as a supplement; a version stored before D-139 reads as its category's kind, else
food.
"""
import base64
import json
import re
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_pack_kind import reading, st  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

TOKEN = "test-token-pack-kind"
TABLET = ["Calcium carbonate", "Microcrystalline cellulose", "Magnesium stearate"]
DRUG = [{"text": "Ayurvedic Medicine Mfg. Lic. No. A-2755", "face": "back"}]


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


def post(barcode, v):
    tag = uuid.uuid4().bytes
    files = {"back": ("b.jpg", b"\xff\xd8\xff\xe0back" + tag, "image/jpeg"),
             "front": ("f.jpg", b"\xff\xd8\xff\xe0front" + tag, "image/jpeg")}
    r = TestClient(main.app).post("/scan", files=files, data={
        "barcode": barcode, "replay": json.dumps(v), "pairing_confirmed": "true"})
    assert r.status_code == 200, r.text
    return r.json()


def item_page(uri, vid):
    [(item_id,)] = q(uri, "SELECT id FROM review_queue WHERE product_version_id = %s", vid)
    c = reviewer()
    return item_id, c, c.get(f"/review/item/{item_id}").text


def test_a_supplement_keeps_its_kind_and_is_served_as_one_once_published(env):
    bc = gtin()
    j = post(bc, reading(TABLET, [st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE")]))
    vid = j["catalogue"]["product_version_id"]
    [(kind, evidence)] = q(env, "SELECT pack_kind, pack_kind_evidence FROM product_versions WHERE id = %s", vid)
    assert kind == "supplement" and evidence["evidence"][0]["text"] == "HEALTH SUPPLEMENT"
    item_id, c, page = item_page(env, vid)
    assert "Kind of pack: health supplement" in page and "HEALTH SUPPLEMENT" in page
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": token})
    r = c.post(f"/review/item/{item_id}/approve", follow_redirects=False, data={
        "csrf": token, "name": "Calcium Tablets", "brand": "Testco", "variant": "", "barcode": "",
        "ingredients": "\n".join(TABLET), "allergen_statement": "", "front_claims": "", "note": "",
        "category": "13.6"})
    assert r.status_code == 303 and "error=" not in r.headers["location"], r.headers["location"]
    hit = TestClient(main.app).post("/scan", data={"barcode": bc}).json()
    assert hit["catalogue"]["source"] == "catalogue"
    assert hit["pack_kind"]["code"] == "supplement" and hit["screen"]["kind"]["code"] == "supplement"
    assert "summary" not in hit["screen"]
    # D-139 phase 2 from the catalogue: the reviewed list's additives, no amounts or statements (they need the
    # photos), and no score.
    ids = [x["id"] for x in hit["screen"]["sections"]]
    assert ids == ["additives"] and hit["verdict"]["score"] is None and hit["display"] is None


def test_a_pack_that_isnt_food_offers_d116s_reason(env):
    j = post(gtin(), reading(["Tulsi", "Mulethi"], [st("Tulsi Mulethi", "front")], licences=DRUG))
    vid = j["catalogue"]["product_version_id"]
    assert j["pack_kind"]["code"] == "not_food"
    item_id, c, page = item_page(env, vid)
    assert "not food: a non-FSSAI licence and no FSSAI licence on the photos" in page
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": token})         # the reject form is for the claimer
    page = c.get(f"/review/item/{item_id}").text
    assert 'value="Not food under the FSS Act: a drug licence, no FSSAI licence (D-116, D-139)"' in page
    assert "Ayurvedic Medicine Mfg. Lic. No. A-2755" in page


def test_food_is_stored_as_food_and_shows_no_kind_panel(env):
    j = post(gtin(), reading(["Whole wheat flour", "Salt"]))
    vid = j["catalogue"]["product_version_id"]
    assert q(env, "SELECT pack_kind FROM product_versions WHERE id = %s", vid) == [("food",)]
    _item, _c, page = item_page(env, vid)
    assert "Kind of pack" not in page


def test_a_version_from_before_d139_reads_as_its_categorys_kind(env):
    assert main._catalogue_kind({"pack_kind": None, "category_code": "13.6"})["code"] == "supplement"
    assert main._catalogue_kind({"pack_kind": None, "category_code": "7.2.1"})["code"] == "food"
    assert main._catalogue_kind({"pack_kind": None, "category_code": None})["code"] == "food"
    stored = main._catalogue_kind({"pack_kind": "infant", "category_code": "13.2",
                                   "pack_kind_evidence": {"evidence": [{"text": "Traditional Food for Infants"}]}})
    assert stored["code"] == "infant" and stored["evidence"][0]["text"] == "Traditional Food for Infants"


def test_compare_refuses_a_stored_infant_scan_even_when_the_client_sends_nothing_about_it(env):
    words = [st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"), st("Infant Formula", "front")]
    j = post(gtin(), reading(["Milk solids", "Lactose", "Vegetable oils"], words))
    assert j["pack_kind"]["code"] == "infant" and j["verdict"] is None
    r = TestClient(main.app).post("/compare", json={"age": "kid", "packs": [
        {"id": j["scan_id"], "name": "Formula", "ingredients": ["Milk solids", "Lactose"]},
        {"id": "other", "name": "Rusk", "ingredients": ["Wheat flour", "Sugar"]}]})
    assert r.status_code == 422 and r.json()["reason"] == "infant_food"
    assert r.json()["pack"] == j["scan_id"]


def test_a_published_infant_pack_is_served_without_any_result(env):
    bc = gtin()
    j = post(bc, reading(["Rice flour", "Milk solids"], [st("Processed Cereal Based Complementary Food", "front")]))
    vid = j["catalogue"]["product_version_id"]
    item_id, c, page = item_page(env, vid)
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": token})
    r = c.post(f"/review/item/{item_id}/approve", follow_redirects=False, data={
        "csrf": token, "name": "Rice Cereal", "brand": "Testco", "variant": "", "barcode": "",
        "ingredients": "Rice flour\nMilk solids", "allergen_statement": "", "front_claims": "", "note": "",
        "category": "13.2"})
    assert r.status_code == 303 and "error=" not in r.headers["location"], r.headers["location"]
    hit = TestClient(main.app).post("/scan", data={"barcode": bc}).json()
    assert hit["catalogue"]["source"] == "catalogue" and hit["pack_kind"]["code"] == "infant"
    assert hit["verdict"] is None and hit["display"] is None and hit["withheld"]["reason"] == "infant_in_shadow"
    assert hit["screen"]["headline"]["text"] == 'This pack says "Processed Cereal Based Complementary Food".'


def test_an_infant_foods_own_checks_are_stored_for_reviewers_and_never_sent(env):
    """D-140 phase 3, in shadow: computed at /scan, kept with the reading, shown on /review only."""
    v = reading(["Rice flour", "Milk solids", "Added flavour (vanilla)", "Hydrogenated vegetable fat"],
                [st("Processed Cereal Based Complementary Food", "front"),
                 st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"), st("The complete Energy Food", "front")])
    j = post(gtin(), v)
    assert "_infant" not in json.dumps(j) and "Energy Food" not in json.dumps(j.get("screen"))
    assert j["verdict"] is None and j["withheld"]["reason"] == "infant_in_shadow"
    vid = j["catalogue"]["product_version_id"]
    [(raw,)] = q(env, "SELECT raw_extraction FROM product_versions WHERE id = %s", vid)
    got = raw["_infant"]
    assert got["type"]["id"] == "processed_cereal"
    assert {s["id"] for s in got["statements"] if not s["found"]} >= {"boiled_water", "not_sole"}
    assert [w["word"] for w in got["words"]] == ["energy food"]
    assert got["free_from"] == [{"entry": "Added flavour (vanilla)", "why": ["flavour"]}]
    assert [h["entry"] for h in got["hydrogenated"]] == ["Hydrogenated vegetable fat"]
    _item, _c, page = item_page(env, vid)
    assert 'id="infant-checks"' in page and "users don't see these" in page
    assert "processed cereal, from" in page and "Not found</strong>: " in page
    assert "No picture of an infant or a woman" in page


def test_a_food_has_no_infant_checks(env):
    j = post(gtin(), reading(["Wheat flour", "Sugar"], [st("Glucose biscuits", "front")]))
    [(raw,)] = q(env, "SELECT raw_extraction FROM product_versions WHERE id = %s", j["catalogue"]["product_version_id"])
    assert "_infant" not in raw
    _item, _c, page = item_page(env, j["catalogue"]["product_version_id"])
    assert 'id="infant-checks"' not in page

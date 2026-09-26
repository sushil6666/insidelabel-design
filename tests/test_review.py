"""Reviewer screen (D-028, D-070, D-076): the only path from a scan to the catalogue."""
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

TOKEN = "test-token-123"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes" + uuid.uuid4().bytes   # unique per run


def vision(ingredients, **kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": "Testco", "name": "Jeera Biscuit", "variant": None,
                     "net_quantity": None, "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
         "ingredients": ingredients, "allergen_statement": "Contains wheat.",
         "front_claims": [], "front_claim_footnotes": [], "extraction_notes": ["Crease over line 2"],
         "confidence": {"ingredients": 0.97, "front_claims": 0.0, "product_identity": 0.8}}
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
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def client(name="asha", token=TOKEN):
    cred = base64.b64encode(f"{name}:{token}".encode()).decode()
    return TestClient(main.app, headers={"Authorization": f"Basic {cred}"})


def csrf(page_html):
    return re.search(r'name="csrf" value="([0-9a-f]+)"', page_html).group(1)


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        return c.execute(sql, args).fetchall()


def scan(ingredients, barcode=None, device_id=None, **kw):
    data = {"replay": vision(ingredients, **kw)}
    if barcode:
        data["barcode"] = barcode
    if device_id:
        data["device_id"] = device_id
    return TestClient(main.app).post("/scan", files={"back": ("b.jpg", JPEG, "image/jpeg")}, data=data)


def take_next(c):
    page = c.get("/review").text
    r = c.post("/review/claim-next", data={"csrf": csrf(page)}, follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def approve(c, item_id, **fields):
    page = c.get(f"/review/item/{item_id}").text
    form = {"csrf": csrf(page), "name": "Jeera Biscuit", "brand": "Testco", "variant": "",
            "barcode": "", "ingredients": "", "allergen_statement": "", "front_claims": "", "note": "",
            "category": "7.2.1"}
    form.update(fields)
    return c.post(f"/review/item/{item_id}/approve", data=form, follow_redirects=False)


# ---------------------------------------------------------------- access

def test_access_control(env):
    anon = TestClient(main.app)
    assert anon.get("/review").status_code == 401
    assert client("asha", token="wrong").get("/review").status_code == 401
    assert client("<bad name>").get("/review").status_code == 401
    assert client().get("/review").status_code == 200
    # a form post without the page's CSRF token is refused
    assert client().post("/review/claim-next", data={}).status_code == 403
    # another reviewer's token doesn't work either
    other = csrf(client("ravi").get("/review").text)
    assert client("asha").post("/review/claim-next", data={"csrf": other}).status_code == 403


def test_photos_need_login_and_a_valid_key(env):
    key = LocalMedia(main.MEDIA.root).put(JPEG, "image/jpeg")
    assert TestClient(main.app).get(f"/review/media/{key}").status_code == 401
    r = client().get(f"/review/media/{key}")
    assert r.status_code == 200 and r.content == JPEG
    assert client().get("/review/media/..%2F..%2Fetc%2Fpasswd").status_code == 404


# ---------------------------------------------------------------- the main path

def test_scan_review_publish_then_barcode_lookup(env):
    uri, bc, dev = env, "8901111111116", str(uuid.uuid4())
    # A reader typo the reviewer will fix: "Jeers" for "Jeera".
    j = scan(["Whole wheat flour (Atta)", "Sugar", "Palm oil", "Jeers (Cumin) 2%", "Salt"],
             barcode=bc, device_id=dev).json()
    vid = j["catalogue"]["product_version_id"]
    assert q(uri, "SELECT back_image_key IS NOT NULL FROM product_versions WHERE id=%s", vid)[0][0]

    c = client("asha")
    item_id = take_next(c)
    page = c.get(f"/review/item/{item_id}").text
    assert "/review/media/" in page and "Jeers (Cumin) 2%" in page
    assert "Crease over line 2" in page                     # model's note shown to the reviewer

    # another reviewer can't decide it
    r = approve(client("ravi"), item_id, ingredients="x")
    assert "Claim+this+item" in r.headers["location"] or "Claim%20this%20item" in r.headers["location"]

    fixed = "Whole wheat flour (Atta)\nSugar\nPalm oil\nJeera (Cumin) 2%\nSalt"
    r = approve(c, item_id, ingredients=fixed, barcode=bc, allergen_statement="Contains wheat.")
    assert r.status_code == 303 and r.headers["location"] == "/review"

    status, current, ings = q(uri, "SELECT status, is_current, ingredients FROM product_versions WHERE id=%s", vid)[0]
    assert (status, current) == ("published", True) and ings[3] == "Jeera (Cumin) 2%"
    assert q(uri, "SELECT status, resolution FROM review_queue WHERE id=%s", item_id)[0] == ("done", "published")
    # findings rebuilt from the corrected list, every one with evidence
    quotes = [r[0] for r in q(uri, """SELECT e.quoted_text FROM evidence e WHERE e.product_version_id=%s""", vid)]
    assert all("Jeers" not in (x or "") for x in quotes)

    # barcode alone now serves the reviewed version
    k = TestClient(main.app).post("/scan", data={"barcode": bc}).json()
    assert k["catalogue"]["source"] == "catalogue" and k["extracted"]["ingredients"][3] == "Jeera (Cumin) 2%"

    # D-070: the install that sent it sees it's ready
    u = TestClient(main.app).get("/updates", params={"device_id": dev}).json()["updates"]
    assert u and u[0]["ready"] is True and u[0]["product_version_id"] == vid


def test_reformulation_shows_a_diff_and_keeps_history(env):
    uri, bc = env, "8902222222227"
    scan(["Wheat flour", "Sugar", "Salt"], barcode=bc)
    c = client()
    approve(c, take_next(c), ingredients="Wheat flour\nSugar\nSalt", barcode=bc)
    scan(["Wheat flour", "Sugar", "Salt", "Preservative (INS 282)"], barcode=bc)   # reformulated
    item_id = take_next(c)
    page = c.get(f"/review/item/{item_id}").text
    assert "Changed from the published version" in page
    assert re.search(r'class="added">Preservative \(INS 282\)', page)
    approve(c, item_id, ingredients="Wheat flour\nSugar\nSalt\nPreservative (INS 282)", barcode=bc)
    rows = q(uri, """SELECT v.version_no, v.is_current, v.valid_to IS NOT NULL FROM product_versions v
                       JOIN products p ON p.id = v.product_id WHERE p.barcode=%s ORDER BY version_no""", bc)
    assert rows == [(1, False, True), (2, True, False)]


def test_reported_mistake_on_published_pack_creates_new_version(env):
    uri, bc = env, "8903333333338"
    sid = scan(["Rice flour", "Salt"], barcode=bc).json()["scan_id"]
    c = client()
    approve(c, take_next(c), ingredients="Rice flour\nSalt", barcode=bc)
    TestClient(main.app).post("/report", json={"scan_id": sid, "field": "ingredients",
                                               "note": "sesame is on the pack"})
    item_id = take_next(c)
    assert "sesame is on the pack" in c.get(f"/review/item/{item_id}").text
    approve(c, item_id, ingredients="Rice flour\nSesame seeds\nSalt", barcode=bc)
    assert q(uri, "SELECT resolution FROM review_queue WHERE id=%s", item_id)[0][0] == "published_new_version"
    cur = q(uri, """SELECT v.ingredients, v.source FROM product_versions v JOIN products p ON p.id=v.product_id
                     WHERE p.barcode=%s AND v.is_current""", bc)[0]
    assert cur == (["Rice flour", "Sesame seeds", "Salt"], "reviewer")
    assert q(uri, "SELECT status FROM corrections WHERE scan_id=%s", sid)[0][0] == "accepted"


def test_unreadable_scan_can_be_transcribed_by_reviewer(env):
    """D-070: 'send it to us' - the reviewer types the list from the stored photo."""
    uri = env
    r = scan(["x"], back_status="unreadable")
    sid = r.json()["scan_id"]
    with psycopg.connect(uri) as c_:
        c_.execute("INSERT INTO review_queue (kind, scan_id) VALUES ('send_to_us', %s)", (sid,))
    c = client()
    item_id = take_next(c)
    assert "/review/media/" in c.get(f"/review/item/{item_id}").text     # the photo is there
    approve(c, item_id, name="Plain Rusk", ingredients="Wheat flour\nSugar\nYeast")
    assert q(uri, "SELECT resolution FROM review_queue WHERE id=%s", item_id)[0][0] == "published_new_version"


def test_reject_needs_a_reason_and_blocks_the_version(env):
    uri = env
    vid = scan(["Something", "Blurry"]).json()["catalogue"]["product_version_id"]
    c = client()
    item_id = take_next(c)
    tok = csrf(c.get(f"/review/item/{item_id}").text)
    r = c.post(f"/review/item/{item_id}/reject", data={"csrf": tok, "reason": ""}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    c.post(f"/review/item/{item_id}/reject", data={"csrf": tok, "reason": "photo unusable"})
    assert q(uri, "SELECT status FROM product_versions WHERE id=%s", vid)[0][0] == "rejected"
    assert q(uri, "SELECT resolution_note FROM review_queue WHERE id=%s", item_id)[0][0] == "photo unusable"


def test_barcode_belonging_to_another_product_is_refused(env):
    bc = "8904444444449"
    scan(["Oats"], barcode=bc)
    c = client()
    approve(c, take_next(c), name="Oats", ingredients="Oats", barcode=bc)
    scan(["Corn flakes"])                                     # different pack, no barcode
    r = approve(c, take_next(c), name="Flakes", ingredients="Corn flakes", barcode=bc)
    assert "already+belongs" in r.headers["location"] or "already%20belongs" in r.headers["location"]


def test_label_text_is_escaped(env):
    scan(["<script>alert(1)</script>", "Sugar"])
    c = client()
    page = c.get(f"/review/item/{take_next(c)}").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    tok = csrf(page)
    item_id = int(re.search(r"<h1[^>]*>#(\d+)", page).group(1))
    c.post(f"/review/item/{item_id}/release", data={"csrf": tok})


# ---------------------------------------------------------------- categories (D-058)

def take(c, scan_response):
    """Claim the review item created by this scan (not just the oldest open one)."""
    vid = scan_response.json()["catalogue"]["product_version_id"]
    item_id = q(routes.SERVICE.conninfo, "SELECT id FROM review_queue WHERE product_version_id = %s", vid)[0][0]
    c.post(f"/review/item/{item_id}/claim", data={"csrf": csrf(c.get("/review").text)})
    return item_id


def test_fssai_categories_are_loaded(env):
    rows = dict(q(env, "SELECT code, name FROM categories"))
    assert len(rows) == 271
    assert rows["7.2.1"] == "Cakes, cookies and pies"
    assert rows["14.1.4.1"] == "Carbonated water-based flavoured drinks"
    parent = q(env, """SELECT p.code FROM categories c JOIN categories p ON p.id = c.parent_id
                       WHERE c.code = '7.2.1'""")[0][0]
    assert parent == "7.2"


def test_approve_needs_a_known_category_and_stores_it(env):
    bc = "8905555555550"
    c = client()
    item_id = take(c, scan(["Wheat flour", "Sugar", "Cocoa solids"], barcode=bc))
    for bad in ("", "99.9"):
        r = approve(c, item_id, ingredients="Wheat flour\nSugar\nCocoa solids", barcode=bc, category=bad)
        assert "error=" in r.headers["location"]
    approve(c, item_id, ingredients="Wheat flour\nSugar\nCocoa solids", barcode=bc, category="7.2.1")
    assert q(env, """SELECT k.code FROM products p JOIN categories k ON k.id = p.category_id
                     WHERE p.barcode = %s""", bc)[0][0] == "7.2.1"


def test_page_preselects_the_stored_category(env):
    bc = "8906666666661"
    c = client()
    approve(c, take(c, scan(["Potato", "Palm oil", "Salt"], barcode=bc)), name="Chips", ingredients="Potato\nPalm oil\nSalt", barcode=bc, category="15.1")
    item_id = take(c, scan(["Potato", "Palm oil", "Salt", "Sugar"], barcode=bc))   # reformulation
    page = c.get(f"/review/item/{item_id}").text
    assert re.search(r'<option value="15\.1" selected>', page)
    assert len(re.findall(r"<option [^>]*selected", page)) == 1

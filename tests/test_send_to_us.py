"""
"Send it to us" (D-070): after two refused scans the app can hand the photos
to a reviewer, and /updates reports back when the pack is ready.

The server checks what the app claims: the scans must be this install's own,
refused, and at least two. Model answers are replayed from JSON.
"""
import base64
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import routes  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402

c = TestClient(main.app)
TOKEN = "send-token-123"


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": ["Sugar, Salt"], "ingredient_count": 2, "ingredients": ["Sugar", "Salt"],
         "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
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
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri
    mp.undo()
    main.STORE, main.MEDIA, routes.SERVICE, routes.MEDIA = saved


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def photo():
    return b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes          # a different "photo" each time


def refused(dev, barcode=None):
    data = {"replay": vision(back_status="unreadable"), "device_id": dev}
    if barcode:
        data["barcode"] = barcode
    r = c.post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")}, data=data)
    assert r.status_code == 422
    return r.json()["scan_id"]


def send(dev, scan_ids):
    return c.post("/send-to-us", json={"device_id": dev, "scan_ids": scan_ids})


def test_two_refused_scans_go_to_the_review_queue(env):
    dev = str(uuid.uuid4())
    a, b = refused(dev), refused(dev, barcode="8901000000037")
    r = send(dev, [a, b])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "received" and j["review_id"]
    q = row(env, "SELECT * FROM review_queue WHERE id = %s", j["review_id"])
    assert q["kind"] == "send_to_us" and q["status"] == "open"
    assert str(q["scan_id"]) == b                                    # the latest attempt
    assert [str(x) for x in q["attempt_scan_ids"]] == [a]
    assert str(q["notify_user_id"]) == dev                           # /updates reports back
    for sid in (a, b):                                               # D-080: kept for the reviewer
        assert row(env, "SELECT evidence_hold FROM scans WHERE id = %s", sid)["evidence_hold"] is True


def test_sending_twice_queues_once(env):
    dev = str(uuid.uuid4())
    ids = [refused(dev), refused(dev)]
    first, again = send(dev, ids).json(), send(dev, ids).json()
    assert again["review_id"] == first["review_id"] and again.get("duplicate") is True


def test_one_refusal_is_not_enough(env):
    dev = str(uuid.uuid4())
    r = send(dev, [refused(dev)])
    assert r.status_code == 422 and r.json()["error"] == "need_two_attempts"


def test_a_scan_with_a_result_is_not_sent(env):
    dev = str(uuid.uuid4())
    ok = c.post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")},
                data={"replay": vision(), "device_id": dev}).json()["scan_id"]
    r = send(dev, [refused(dev), ok])
    assert r.status_code == 422 and r.json()["error"] == "not_refused"


def test_only_your_own_scans(env):
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    r = send(mine, [refused(mine), refused(theirs)])
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert send(mine, [str(uuid.uuid4()), refused(mine)]).status_code == 404


def test_bad_input(env):
    assert send("not-a-uuid", [str(uuid.uuid4())] * 2).status_code == 422
    dev = str(uuid.uuid4())
    assert send(dev, ["x", "y"]).status_code == 422
    assert send(dev, [str(uuid.uuid4()) for _ in range(9)]).status_code == 422


def test_needs_the_database(monkeypatch):
    monkeypatch.setattr(main, "STORE", None)
    assert send(str(uuid.uuid4()), [str(uuid.uuid4())] * 2).status_code == 503


def test_reviewer_sees_every_attempt_and_the_barcode(env):
    dev = str(uuid.uuid4())
    a, b = refused(dev), refused(dev, barcode="8901000000044")
    rid = send(dev, [a, b]).json()["review_id"]
    d = routes.SERVICE.get(rid)
    assert [str(s["id"]) for s in d["attempts"]] == [a]
    assert d["attempts"][0]["back_image_key"] and d["images"]["back"]
    cred = base64.b64encode(f"asha:{TOKEN}".encode()).decode()
    page = TestClient(main.app, headers={"Authorization": f"Basic {cred}"}).get(f"/review/item/{rid}").text
    assert d["attempts"][0]["back_image_key"] in page                # both photos on the page
    assert 'value="8901000000044"' in page                          # barcode the app read, pre-filled
    assert "Nothing was read automatically" in page


def test_published_by_a_reviewer_then_ready_on_updates(env):
    dev = str(uuid.uuid4())
    rid = send(dev, [refused(dev), refused(dev, barcode="8901000000051")]).json()["review_id"]
    svc = routes.SERVICE
    assert svc.claim(rid, "asha")
    out = svc.approve(rid, "asha", {"name": "Jeera Biscuit", "brand": "Testco", "barcode": "8901000000051",
                                    "category": "7.2.1", "ingredients": "Wheat flour\nSugar\nSalt"})
    assert out["resolution"] == "published_new_version"
    ups = c.get("/updates", params={"device_id": dev}).json()["updates"]
    assert [(u["kind"], u["ready"], u["product_name"]) for u in ups] == [("send_to_us", True, "Jeera Biscuit")]
    # …and the barcode now answers from the catalogue.
    assert c.post("/scan", data={"barcode": "8901000000051"}).status_code == 200


def test_sending_is_rate_limited(env, monkeypatch):
    from insidelabel import ratelimit
    monkeypatch.setattr(ratelimit.LIMITER, "rules", {**ratelimit.RULES,
                                                     "send_to_us": {"device": [(1, 3600)]}})
    dev = str(uuid.uuid4())
    assert send(dev, [refused(dev), refused(dev)]).status_code == 200
    assert send(dev, [refused(dev), refused(dev)]).status_code == 429

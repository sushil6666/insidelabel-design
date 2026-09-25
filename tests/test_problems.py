"""
Reproducing what went wrong (D-092): request ids, a trace on every scan row,
"Report a problem", and unhandled errors stored as server reports.

Vision calls are replayed from recorded JSON, so nothing here spends money.
"""
import base64
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel import trace  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402

c = TestClient(main.app, raise_server_exceptions=False)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}
DEV = str(uuid.uuid4())
ING = ["Refined wheat flour (Maida)", "Sugar", "Milk solids", "Preservative (INS 211)"]


def vision(ingredients=ING, **kw):
    v = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Testco", "name": "Trace Biscuit", "variant": None,
                    "net_quantity": "100 g", "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": "Testco", "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": "Contains wheat, milk.",
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.9},
    }
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def db(fresh_db):
    uri = fresh_db[0]
    old = main.STORE
    main.STORE = Store(uri)
    yield uri
    main.STORE = old


def row(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        conn.row_factory = psycopg.rows.dict_row
        return conn.execute(sql, args).fetchone()


def scan(rid, **data):
    return c.post("/scan", files=BACK, data={"device_id": DEV, **data}, headers={"X-Request-ID": rid})


# ---------------------------------------------------------------- request ids (no DB needed)

def test_every_response_carries_a_request_id():
    mine = str(uuid.uuid4())
    assert c.get("/health", headers={"X-Request-ID": mine}).headers["x-request-id"] == mine
    # Anything that isn't a plain id is replaced, never echoed.
    got = c.get("/health", headers={"X-Request-ID": "<script>"}).headers["x-request-id"]
    assert got != "<script>" and uuid.UUID(got)


def test_error_bodies_quote_the_request_id():
    r = c.post("/scan", data={"barcode": "12"})
    assert r.status_code == 422 and r.json()["request_id"] == r.headers["x-request-id"]


def test_health_names_build_and_data():
    j = c.get("/health").json()
    assert j["build"] == trace.BUILD and len(j["data_version"]) == 12


def test_problem_needs_the_database():
    old, main.STORE = main.STORE, None
    try:
        assert c.post("/problem", json={"comment": "x"}).status_code == 503
    finally:
        main.STORE = old


# ---------------------------------------------------------------- traces on scan rows

def test_a_verdict_scan_can_be_replayed(db):
    rid, v = str(uuid.uuid4()), vision()
    prof = [{"ref": "p1", "age": "kid", "avoid": ["milk"]}]
    r = scan(rid, replay=v, barcode="8901000000013", profiles=json.dumps(prof), who="Aarav")
    assert r.status_code == 200
    s = row(db, "SELECT * FROM scans WHERE id = %s", r.json()["scan_id"])
    assert s["request_id"] == rid and s["model_raw"] == v            # exactly what the model said
    assert s["build"] == trace.BUILD and s["data_version"] == trace.DATA_VERSION
    assert s["request"]["profiles"] == prof and s["request"]["barcode"] == "8901000000013"
    assert "who" not in s["request"] and "Aarav" not in json.dumps(s["request"])   # D-074
    assert "vision_ms" in s["timings"] and "ocr_ms" in s["timings"]


def test_a_refused_scan_keeps_the_model_answer(db):
    rid, v = str(uuid.uuid4()), vision(back_status="unreadable")
    r = scan(rid, replay=v)
    assert r.status_code == 422 and r.json()["request_id"] == rid
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", rid)
    assert s["outcome"] == "refused" and s["model_raw"] == v


def test_an_unparseable_model_answer_is_kept(db):
    rid = str(uuid.uuid4())
    r = scan(rid, replay="this is not json {")
    assert r.status_code == 502
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", rid)
    assert s["outcome"] == "vision_failed" and s["model_raw"] == "this is not json {"


def test_a_read_with_nothing_parseable_is_recorded(db):
    # Used to raise 422 without storing anything.
    rid = str(uuid.uuid4())
    r = scan(rid, replay=vision(ingredients=["..."]))
    assert r.status_code == 422
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", rid)
    assert s is not None and s["outcome"] == "refused" and s["model_raw"]


# ---------------------------------------------------------------- report a problem

def test_report_links_scans_from_the_trail_and_holds_the_photos(db):
    rid = str(uuid.uuid4())
    sid = scan(rid, replay=vision(back_status="unreadable")).json()["scan_id"]
    events = [{"t": 1, "type": "route", "to": "photo"},
              {"t": 2, "type": "api", "path": "/scan", "status": 422, "request_id": rid},
              {"t": 3, "type": "route", "to": "result", "nickname": "Aarav"}]
    r = c.post("/problem", json={"kind": "user", "device_id": DEV, "request_id": rid,
                                  "comment": "It keeps saying retake", "app_version": "web-1",
                                  "client": {"ua": "test", "profiles": [{"ref": "p1", "name": "Aarav"}]},
                                  "events": events})
    assert r.status_code == 200
    j = r.json()
    assert j["scan_id"] == sid
    rep = row(db, "SELECT * FROM problem_reports WHERE id = %s", j["problem_id"])
    assert rep["build"] == trace.BUILD and rep["events"][1]["request_id"] == rid
    assert "Aarav" not in json.dumps(rep["events"]) + json.dumps(rep["client"])   # D-074
    assert row(db, "SELECT evidence_hold FROM scans WHERE id = %s", sid)["evidence_hold"] is True

    full = main.STORE.problem(j["problem_id"])
    assert [str(s["id"]) for s in full["scans"]] == [sid]


def test_a_user_report_holds_every_scan_in_its_trail(db):
    earlier, last = str(uuid.uuid4()), str(uuid.uuid4())
    a = scan(earlier, replay=vision()).json()["scan_id"]
    b = scan(last, replay=vision(back_status="unreadable")).json()["scan_id"]
    events = [{"type": "api", "path": "/scan", "status": 200, "request_id": earlier},
              {"type": "api", "path": "/scan", "status": 422, "request_id": last}]
    c.post("/problem", json={"kind": "user", "device_id": DEV, "request_id": last, "events": events})
    for sid in (a, b):
        assert row(db, "SELECT evidence_hold FROM scans WHERE id = %s", sid)["evidence_hold"] is True
    # A crash report holds nothing: nobody agreed to keep those photos.
    other = str(uuid.uuid4())
    s3 = scan(other, replay=vision()).json()["scan_id"]
    c.post("/problem", json={"kind": "auto", "device_id": DEV, "signature": "x@y:1",
                             "events": [{"type": "api", "path": "/scan", "request_id": other}]})
    assert row(db, "SELECT evidence_hold FROM scans WHERE id = %s", s3)["evidence_hold"] is False


def test_repeated_crash_reports_count_once(db):
    body = {"kind": "auto", "device_id": DEV, "signature": "TypeError@app.js:10", "events": []}
    a, b = c.post("/problem", json=body).json(), c.post("/problem", json=body).json()
    assert b["problem_id"] == a["problem_id"] and b.get("duplicate") is True


def test_reports_are_bounded(db):
    assert c.post("/problem", json={"kind": "server"}).status_code == 422
    big = [{"type": "x", "blob": "a" * 1000}] * 150
    assert c.post("/problem", json={"events": big}).status_code == 413
    assert c.post("/problem", json={"events": [{}] * 201}).status_code == 422


def test_an_unhandled_error_becomes_a_server_report(db, monkeypatch):
    def boom(_raw):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(main.engine, "analyze", boom)
    rid = str(uuid.uuid4())
    r = c.post("/analyze", json={"raw_ingredients": "Sugar, Salt"}, headers={"X-Request-ID": rid})
    assert r.status_code == 500 and r.json() == {
        "error": "server_error", "detail": "Something went wrong on our side.", "request_id": rid}
    rep = row(db, "SELECT * FROM problem_reports WHERE request_id = %s", rid)
    assert rep["kind"] == "server" and "engine exploded" in rep["server_error"]
    assert rep["signature"].startswith("RuntimeError@")


# ---------------------------------------------------------------- replay (tools/repro.py)

def test_a_stored_scan_replays_to_what_the_user_saw(db):
    from insidelabel import repro
    rid = str(uuid.uuid4())
    prof = [{"ref": "p1", "age": "toddler", "avoid": ["milk"]}]
    first = scan(rid, replay=vision(), profiles=json.dumps(prof)).json()
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", rid)
    n = row(db, "SELECT count(*) AS n FROM scans")["n"]
    out = repro.replay_scan(s, media=None)
    assert out["status"] == 200
    assert repro.summary(out["screen"]) == repro.summary(first["screen"])
    assert repro.compare(repro.summary(first["screen"]), repro.summary(out["screen"])) == []
    assert row(db, "SELECT count(*) AS n FROM scans")["n"] == n          # a replay writes nothing
    assert any("photo not available" in x for x in out["notes"])


def test_a_catalogue_hit_replays_from_its_own_version(db):
    from insidelabel import repro
    bc = "8901000000020"
    j = scan(str(uuid.uuid4()), replay=vision(), barcode=bc).json()
    with psycopg.connect(db) as conn:
        conn.execute("SELECT publish_version(%s, 'tester')", (j["catalogue"]["product_version_id"],))
    rid = str(uuid.uuid4())
    hit = c.post("/scan", data={"barcode": bc, "profiles": json.dumps([{"ref": "p1", "age": "kid", "avoid": ["milk"]}])},
                 headers={"X-Request-ID": rid}).json()
    s = row(db, "SELECT * FROM scans WHERE request_id = %s", rid)
    assert s["cache_hit"] is True and s["request"]["profiles"][0]["avoid"] == ["milk"]
    out = repro.replay_scan(s, hit=main.STORE.version_hit(s["product_version_id"]))
    assert repro.summary(out["screen"]) == repro.summary(hit["screen"])


def test_a_model_that_never_answered_is_not_replayed(db):
    from insidelabel import repro
    out = repro.replay_scan({"outcome": "vision_unavailable", "model_raw": None, "request": {}})
    assert out["status"] is None and "never answered" in out["notes"][-1]


def test_model_retries_are_on_the_trace(db, monkeypatch):
    from insidelabel.extraction.providers import gemini
    real = gemini.analyze_images

    def busy_then_ok(images, raw_response=None, on_attempt=None, **kw):
        on_attempt(1, 2.04, RuntimeError("503 overloaded"))     # what _with_retries reports
        return real(images, raw_response=raw_response, **kw)
    monkeypatch.setattr(main.gemini, "analyze_images", busy_then_ok)
    rid = str(uuid.uuid4())
    assert scan(rid, replay=vision()).status_code == 200
    t = row(db, "SELECT timings FROM scans WHERE request_id = %s", rid)["timings"]
    assert t["vision_retries"] == [{"attempt": 1, "wait_s": 2.0, "error": "RuntimeError"}]


# ---------------------------------------------------------------- setup alarms

class _SdkError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"{code} {msg}")
        self.code = code


@pytest.mark.parametrize("code,msg,kind", [
    (402, "RESOURCE_EXHAUSTED. Your prepayment credits are depleted.", "config"),
    (403, "PERMISSION_DENIED", "config"),
    (401, "UNAUTHENTICATED", "config"),
    (400, "API key not valid. Please pass a valid API key.", "config"),
    (503, "UNAVAILABLE high demand", "busy"),
    (429, "RESOURCE_EXHAUSTED rate limit", "busy"),
    (400, "Invalid JSON payload", "other"),
])
def test_google_errors_are_sorted_by_who_can_fix_them(monkeypatch, code, msg, kind):
    from insidelabel.extraction.providers import gemini

    class FakeModels:
        def generate_content(self, **kw):
            raise _SdkError(code, msg)

    class FakeClient:
        def __init__(self, **kw):
            self.models = FakeModels()
    monkeypatch.setattr(gemini.genai, "Client", FakeClient)
    with pytest.raises(gemini.VisionError) as e:
        gemini.call_gemini_sdk([(PNG, "image/png", "back")], api_key="k")
    got = ("config" if isinstance(e.value, gemini.VisionConfigError)
           else "busy" if isinstance(e.value, gemini.VisionUnavailable) else "other")
    assert got == kind


def test_out_of_credit_alarms_once_and_tells_the_user_plainly(db, monkeypatch):
    from insidelabel.extraction.providers import gemini

    def no_credit(images, raw_response=None, **kw):
        err = gemini.VisionConfigError("Gemini setup problem (402): Your prepayment credits are depleted.")
        err.status = 402
        raise err
    monkeypatch.setattr(main.gemini, "analyze_images", no_credit)
    with psycopg.connect(db) as conn:
        conn.execute("DELETE FROM problem_reports WHERE signature = 'vision_config:402'")
    rids = [str(uuid.uuid4()) for _ in range(3)]
    for rid in rids:
        r = scan(rid)
        assert r.status_code == 503 and r.json()["error"] == "vision_not_configured"
        assert "credit" not in r.json()["detail"]             # the user isn't told about our billing
    n = row(db, "SELECT count(*) AS n FROM problem_reports WHERE kind = 'server' AND signature = 'vision_config:402'")
    assert n["n"] == 1                                         # three failed scans, one alarm
    rep = row(db, "SELECT * FROM problem_reports WHERE signature = 'vision_config:402'")
    assert "prepayment credits" in rep["server_error"]
    s = row(db, "SELECT outcome, error_code FROM scans WHERE request_id = %s", rids[0])
    assert s == {"outcome": "vision_failed", "error_code": "vision_config:402"}


def test_cloud_vision_setup_failure_raises_an_alarm(db, monkeypatch):
    import io
    import urllib.error
    from insidelabel.extraction.providers import cloud_vision as cv

    def refused(req, timeout=None):
        raise urllib.error.HTTPError(cv.ENDPOINT, 403, "Forbidden", {}, io.BytesIO(b'{"error":"billing"}'))
    monkeypatch.setenv("GOOGLE_VISION_KEY", "test-key")
    monkeypatch.setattr(cv.urllib.request, "urlopen", refused)
    monkeypatch.setattr(cv, "_down_until", 0.0)
    cv._CACHE.clear()
    rid = str(uuid.uuid4())
    assert scan(rid, replay=vision()).status_code == 200        # the scan still works, on Tesseract
    rep = row(db, "SELECT * FROM problem_reports WHERE signature = 'ocr_config:http_403'")
    assert rep and rep["kind"] == "server" and "Tesseract" in rep["server_error"]
    assert cv.take_alarm() is None                             # taken once

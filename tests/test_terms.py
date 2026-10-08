"""
"Before you start" (D-105): every install agrees, before its first scan, to
photograph only real packs, never AI-made or edited pictures or screenshots,
and that it is a person, not a program. The server records who agreed to which
version; the app asks (D-184: the server-side gate went with the invite codes).
A new version of the text asks everyone again.
"""
import base64
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
VISION = json.dumps({
    "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
    "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": None},
    "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
    "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
    "ingredient_lines": ["Sugar, Salt"], "ingredient_count": 2, "ingredients": ["Sugar", "Salt"],
    "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
    "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}})


@pytest.fixture(scope="module")
def env(fresh_db):
    uri = fresh_db[0]
    saved = main.STORE
    main.STORE = Store(uri)
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri
    mp.undo()
    main.STORE = saved


def phone():
    return str(uuid.uuid4())


def scan(dev):
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")}, data={"replay": VISION, "device_id": dev})


def agree(dev, version=None):
    return c.post("/agree", json={"device_id": dev, "terms_version": version or main.TERMS["version"]})


def test_the_terms_say_what_matters():
    t = c.get("/terms").json()
    text = " ".join(t["points"]).lower()
    assert t["version"] and t["agree_label"] and len(t["points"]) >= 4
    for must in ("real person", "real packs", "ai", "screenshot", "checked by a person"):
        assert must in text, must


def test_the_terms_pass_the_wording_lint():
    import test_wording
    t = main.TERMS
    test_wording.assert_clean([t["title"], t["intro"], t["agree_label"], *t["points"]], "terms")


def test_a_new_phone_has_not_agreed(env):
    dev = phone()
    assert c.get("/access", params={"device_id": dev}).json() == {
        "agreed": False, "terms_version": main.TERMS["version"],
        "live_shutter": False}                                       # D-171: off unless switched on


def test_agreeing_is_recorded(env):
    dev = phone()
    r = agree(dev)
    assert r.status_code == 200 and r.json()["status"] == "agreed"
    assert c.get("/access", params={"device_id": dev}).json()["agreed"] is True
    with psycopg.connect(env) as conn:
        row = conn.execute("SELECT terms_version FROM agreements WHERE user_id = %s", (dev,)).fetchone()
    assert row == (main.TERMS["version"],)


def test_agreeing_to_an_old_version_is_refused(env):
    r = agree(phone(), version="2000-01-01")
    assert r.status_code == 409 and r.json()["error"] == "terms_changed"


def test_new_terms_ask_everyone_again(env, monkeypatch):
    dev = phone()
    agree(dev)
    monkeypatch.setitem(main.TERMS, "version", "2099-01-01")
    assert c.get("/access", params={"device_id": dev}).json()["agreed"] is False
    assert agree(dev).status_code == 200
    assert c.get("/access", params={"device_id": dev}).json()["agreed"] is True


def test_the_server_does_not_gate_scans(env):
    # D-184: the app asks; the server's check went with the invite codes (D-102).
    assert scan(phone()).status_code == 200


def test_agree_needs_a_valid_device_and_the_database(monkeypatch):
    assert c.post("/agree", json={"device_id": "nope", "terms_version": main.TERMS["version"]}).status_code == 422
    monkeypatch.setattr(main, "STORE", None)
    assert agree(str(uuid.uuid4())).status_code == 503


def test_the_app_shows_the_agreement_first():
    import os
    app_js = open(os.path.join(main.WEB_DIR, "app.js"), encoding="utf-8").read()
    assert "function agree(" in app_js and '"agree"' in app_js.split("const FIRST_RUN")[1].split("\n")[0]

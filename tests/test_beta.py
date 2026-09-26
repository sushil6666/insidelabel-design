"""
The invite-only web beta (D-102): one code per tester, the server refuses
scans from a phone that hasn't joined, and testers' feedback is stored
against their code. Model answers are replayed from JSON.
"""
import base64
import importlib.util
import json
import os
import re
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cli():
    spec = importlib.util.spec_from_file_location("beta_cli", os.path.join(ROOT, "tools", "beta.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def env(fresh_db):
    uri = fresh_db[0]
    saved = (main.STORE, main.INVITE_ONLY)
    main.STORE = Store(uri)
    main.INVITE_ONLY = True
    mp = pytest.MonkeyPatch()
    mp.setenv("INSIDELABEL_OCR", "tesseract")
    mp.setattr(main.ocr_check, "AVAILABLE", False)
    yield uri
    mp.undo()
    main.STORE, main.INVITE_ONLY = saved


def new_codes(uri, n=1, label=None):
    return main.STORE.create_invites(n, label=label)


def scan(dev):
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
                  data={"replay": VISION, "device_id": dev})


def join(code, dev):
    """Join with a code, and agree to "Before you start" (D-105) as the app does next."""
    r = c.post("/join", json={"code": code, "device_id": dev})
    if r.status_code == 200:
        c.post("/agree", json={"device_id": dev, "terms_version": main.TERMS["version"]})
    return r


# ---------------------------------------------------------------- codes

def test_codes_are_unambiguous_and_unique(env):
    codes = new_codes(env, 20)
    assert len(set(codes)) == 20
    assert all(re.fullmatch(r"[A-HJKMNP-Z2-9]{8}", k) for k in codes)     # no 0/O, 1/I/L


def test_a_phone_without_a_code_cannot_scan(env, monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("model called for a phone that hasn't joined")
    monkeypatch.setattr(main.gemini, "analyze_images", no_model)
    dev = str(uuid.uuid4())
    r = scan(dev)
    assert r.status_code == 403 and r.json()["error"] == "invite_required"
    assert c.post("/scan", files={"back": ("b.png", PNG, "image/png")}, data={"replay": VISION}).status_code == 403
    with psycopg.connect(env) as conn:                              # refused before anything is stored
        assert conn.execute("SELECT count(*) FROM scans WHERE user_id = %s", (dev,)).fetchone()[0] == 0


def test_joining_opens_the_app(env):
    (code,) = new_codes(env, label="T01")
    dev = str(uuid.uuid4())
    a = c.get("/access", params={"device_id": dev}).json()
    assert (a["invite_only"], a["joined"]) == (True, False)
    r = join(code.lower()[:4] + "-" + code.lower()[4:], dev)          # typed loosely: case and a dash
    assert r.status_code == 200 and r.json()["status"] == "joined"
    a = c.get("/access", params={"device_id": dev}).json()
    assert (a["invite_only"], a["joined"], a["agreed"]) == (True, True, True)
    assert scan(dev).status_code == 200
    assert join(code, dev).status_code == 200                        # joining again is harmless


def test_one_code_serves_a_few_devices_not_everyone(env):
    (code,) = new_codes(env)
    devs = [str(uuid.uuid4()) for _ in range(4)]
    assert [join(code, d).status_code for d in devs] == [200, 200, 200, 409]   # phone + laptop + spare
    assert join(code, devs[3]).json()["error"] == "code_full"


def test_bad_and_revoked_codes(env):
    assert join("ZZZZZZZZ", str(uuid.uuid4())).status_code == 404
    assert join("", str(uuid.uuid4())).status_code == 404
    (code,) = new_codes(env)
    dev = str(uuid.uuid4())
    join(code, dev)
    main.STORE.revoke_invite(code)
    assert scan(dev).status_code == 403                              # revoking locks the tester out
    assert join(code, str(uuid.uuid4())).status_code == 410


def test_guessing_codes_is_slowed_down(env):
    dev = str(uuid.uuid4())
    codes = [join(f"AAAAAAA{i}", dev).status_code for i in range(2, 9)] + \
            [join(f"BBBBBBB{i}", dev).status_code for i in range(2, 9)]
    assert 429 in codes


def test_invite_only_off_leaves_the_app_open(env, monkeypatch):
    monkeypatch.setattr(main, "INVITE_ONLY", False)
    assert scan(str(uuid.uuid4())).status_code == 200
    assert c.get("/access", params={"device_id": str(uuid.uuid4())}).json()["invite_only"] is False


def test_invite_only_follows_the_environment(monkeypatch):
    monkeypatch.setattr(main, "INVITE_ONLY", None)
    monkeypatch.delenv("INSIDELABEL_INVITE_ONLY", raising=False)
    assert main._invite_only() is False
    monkeypatch.setenv("INSIDELABEL_INVITE_ONLY", "on")
    assert main._invite_only() is True


def test_invite_only_without_a_database_refuses(monkeypatch):
    monkeypatch.setattr(main, "STORE", None)
    monkeypatch.setattr(main, "INVITE_ONLY", True)
    assert scan(str(uuid.uuid4())).status_code == 503


# ---------------------------------------------------------------- feedback

def test_feedback_is_stored_against_the_testers_code(env):
    (code,) = new_codes(env, label="T02")
    dev = str(uuid.uuid4())
    join(code, dev)
    r = c.post("/feedback", json={"device_id": dev, "rating": 4, "comment": "Result was clear, took 12 s",
                                  "screen": "result", "app_version": "web-9"})
    assert r.status_code == 200
    with psycopg.connect(env) as conn:
        row = conn.execute("SELECT invite_code, rating, comment, screen FROM feedback WHERE id = %s",
                           (r.json()["feedback_id"],)).fetchone()
    assert row == (code, 4, "Result was clear, took 12 s", "result")


def test_feedback_needs_a_code_and_words(env):
    dev = str(uuid.uuid4())
    assert c.post("/feedback", json={"device_id": dev, "comment": "hi"}).status_code == 403
    (code,) = new_codes(env)
    join(code, dev)
    assert c.post("/feedback", json={"device_id": dev, "comment": "   "}).status_code == 422
    assert c.post("/feedback", json={"device_id": dev, "comment": "x", "rating": 9}).status_code == 422
    assert c.post("/feedback", json={"device_id": dev, "comment": "x" * 4001}).status_code == 422


# ---------------------------------------------------------------- tools/beta.py

def test_the_cli_makes_links_and_shows_who_came_back(env, capsys):
    cli = _cli()
    cli.main(["--db", env, "invite", "2", "--label", "cousins", "--base", "https://insidelabel.example"])
    out = capsys.readouterr().out
    links = re.findall(r"https://insidelabel\.example/app/#/join/([A-Z2-9]{8})", out)
    assert len(links) == 2
    dev = str(uuid.uuid4())
    join(links[0], dev)
    scan(dev)
    c.post("/feedback", json={"device_id": dev, "comment": "Nice"})
    cli.main(["--db", env, "list"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if links[0] in ln)
    assert "cousins" in line and re.search(r"\b1 device", line) and re.search(r"\b1 scan", line)
    cli.main(["--db", env, "feedback"])
    assert "Nice" in capsys.readouterr().out
    cli.main(["--db", env, "reset", links[0]])
    assert c.get("/access", params={"device_id": dev}).json()["joined"] is False

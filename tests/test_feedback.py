"""
"Send feedback" (D-102): what a user thinks, stored with their install, read with
tools/feedback.py. D-184: no invite codes, so any install can send it.
"""
import importlib.util
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402

c = TestClient(main.app)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cli():
    spec = importlib.util.spec_from_file_location("feedback_cli", os.path.join(ROOT, "tools", "feedback.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def env(fresh_db):
    uri = fresh_db[0]
    saved = main.STORE
    main.STORE = Store(uri)
    yield uri
    main.STORE = saved


def test_feedback_is_stored_with_the_install(env):
    dev = str(uuid.uuid4())
    r = c.post("/feedback", json={"device_id": dev, "rating": 4, "comment": "Result was clear, took 12 s",
                                  "screen": "result", "app_version": "web-9"})
    assert r.status_code == 200
    with psycopg.connect(env) as conn:
        row = conn.execute("SELECT user_id::text, invite_code, rating, comment, screen FROM feedback WHERE id = %s",
                           (r.json()["feedback_id"],)).fetchone()
    assert row == (dev, None, 4, "Result was clear, took 12 s", "result")


def test_feedback_needs_words(env):
    dev = str(uuid.uuid4())
    assert c.post("/feedback", json={"device_id": dev, "comment": "   "}).status_code == 422
    assert c.post("/feedback", json={"device_id": dev, "comment": "x", "rating": 9}).status_code == 422
    assert c.post("/feedback", json={"device_id": dev, "comment": "x" * 4001}).status_code == 422


def test_there_is_no_join_any_more(env):
    # D-184: the invite-only beta is gone; /access no longer speaks of codes.
    dev = str(uuid.uuid4())
    assert c.post("/join", json={"code": "K7PM4QXT", "device_id": dev}).status_code in (404, 405)
    a = c.get("/access", params={"device_id": dev}).json()
    assert set(a) == {"agreed", "terms_version", "live_shutter"}


def test_the_cli_shows_feedback_newest_first(env, capsys):
    dev = str(uuid.uuid4())
    c.post("/feedback", json={"device_id": dev, "comment": "First"})
    c.post("/feedback", json={"device_id": dev, "comment": "Nice"})
    _cli().main(["--db", env, "--limit", "2"])
    out = capsys.readouterr().out
    assert out.index("Nice") < out.index("First")

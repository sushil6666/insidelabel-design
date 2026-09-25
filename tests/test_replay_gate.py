"""
The `replay` field is off unless switched on (D-101).

A recorded model answer skips the paid model step and would land in the review
queue as a pending version; on a public server anyone could invent one. The
suite switches it on in conftest.py; these tests switch it off again.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from insidelabel.api import main
from insidelabel import repro

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}


@pytest.fixture
def replay_off(monkeypatch):
    monkeypatch.delenv("INSIDELABEL_ALLOW_REPLAY", raising=False)


def test_refused_when_not_switched_on(replay_off, monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("a refused replay must not reach the model")
    monkeypatch.setattr(main.gemini, "analyze_images", no_model)
    r = c.post("/scan", files=BACK, data={"replay": '{"ingredients": ["Sugar"]}'})
    assert r.status_code == 403 and r.json()["error"] == "replay_disabled"


def test_empty_replay_box_is_not_a_replay(replay_off):
    # /docs sends empty boxes; that must not trip the gate.
    r = c.post("/scan", data={"replay": "", "barcode": ""})
    assert r.status_code == 422 and r.json()["error"] == "no_images"


def test_repro_still_replays_with_the_gate_off(replay_off):
    with repro.no_storage():
        assert main._replay_allowed()
    assert not main._replay_allowed()

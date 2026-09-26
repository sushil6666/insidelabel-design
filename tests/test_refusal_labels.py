"""
Refusals name the photo that's wrong, and don't borrow a name from the other
photo (Sushil's test, 2026-09-26): a screenshot as the back and a real Ziggy
front was refused correctly, but the history read "ZIGGY DONUT CAKE Choco
Vanilla: This doesn't look like a food pack", which says neither which photo
was wrong nor that Ziggy wasn't the problem. fixtures/screenshot_back_ziggy_front.json
is Gemini's real answer for that scan.
"""
import base64
import json
import os

import pytest
from fastapi.testclient import TestClient

from insidelabel.api import main

c = TestClient(main.app)
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = open(os.path.join(HERE, "fixtures", "screenshot_back_ziggy_front.json"), encoding="utf-8").read()
MISMATCH = open(os.path.join(HERE, "fixtures", "pack_mismatch_live.json"), encoding="utf-8").read()
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = ("b.png", PNG, "image/png")


@pytest.fixture(autouse=True)
def no_ocr(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(main.ocr_check, "AVAILABLE", False)


def test_the_back_photo_is_named_when_two_were_sent():
    r = c.post("/scan", files={"back": BACK, "front": ("f.png", PNG, "image/png")}, data={"replay": LIVE})
    assert r.status_code == 422
    s = r.json()["screen"]
    assert s["headline"]["text"].startswith("The back photo")
    assert "back" in s["retake"].lower()


def test_a_refused_scan_does_not_borrow_the_fronts_name():
    r = c.post("/scan", files={"back": BACK, "front": ("f.png", PNG, "image/png")}, data={"replay": LIVE})
    assert r.json()["product"] is None                         # was ZIGGY DONUT CAKE, from the good front


def test_two_packs_do_not_borrow_a_name_either():
    r = c.post("/scan", files={"back": BACK, "front": ("f.png", PNG, "image/png")}, data={"replay": MISMATCH})
    assert r.json()["reliability"]["error"] == "product_mismatch" and r.json()["product"] is None


def test_one_photo_keeps_the_plain_wording():
    v = json.loads(LIVE[LIVE.find("{"):LIVE.rfind("}") + 1])
    v["image_content"] = {"back": "not_food", "front": "not_provided"}
    v["front_status"] = "not_provided"
    r = c.post("/scan", files={"back": BACK}, data={"replay": json.dumps(v)})
    assert r.json()["screen"]["headline"]["text"] == "This doesn't look like a food pack."


def test_the_new_wording_passes_the_lint():
    import test_wording
    from insidelabel.lenses import screen
    test_wording.assert_clean(list(screen.HEADLINE_BACK.values()) + list(screen.RETAKE_BACK.values()), "back-photo texts")

"""
A front of one pack with the back of another (D-108).

Found on 2026-09-26: Patanjali Doodh Biscuits front + Maliban wafer back, with
"both photos are of the same pack" ticked. Gemini said "mismatch" with the
reason; the code threw that away (a mismatch has no matching anchor, by
definition), the tick then trusted the pairing, and Patanjali's front claims
were attached to the wafer. fixtures/pack_mismatch_live.json is that answer.

Now: a mismatch whose evidence names a difference, with nothing checkable
matching across the faces, refuses the scan; the tick can't override it.
A "mismatch" whose own evidence describes sameness (a real Limca bottle once)
stays "can't tell".
"""
import base64
import io
import json
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gtins import gtin
from insidelabel.api import main
from insidelabel.extraction.providers import gemini

c = TestClient(main.app)
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = open(os.path.join(HERE, "fixtures", "pack_mismatch_live.json"), encoding="utf-8").read()
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BOTH = {"back": ("b.png", PNG, "image/png"), "front": ("f.png", PNG, "image/png")}
TWO = [(b"b", "image/jpeg", "back"), (b"f", "image/jpeg", "front")]


@pytest.fixture(autouse=True)
def no_ocr(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(main.ocr_check, "AVAILABLE", False)


def answer(**kw):
    v = json.loads(LIVE[LIVE.find("{"):LIVE.rfind("}") + 1])
    v.update(kw)
    return json.dumps(v)


def test_a_reasoned_mismatch_is_kept():
    v, corrections = gemini.analyze_images(TWO, raw_response=LIVE)
    assert v["product_match"]["status"] == "mismatch"


def test_a_mismatch_argued_from_sameness_stays_cant_tell():
    # The real Limca answer that once said "mismatch" while citing what matched.
    limca = answer(product_match={"status": "mismatch", "evidence": [
        "The Coca-Cola Company printed on both front and back label side markings",
        "Matching green/red design scheme of Limca carbonated soft drink bottle"]},
        front_identity={"brand": "Limca", "name": "Limca", "manufacturer": None},
        back_identity={"brand": "The Coca-Cola Company", "name": None,
                       "manufacturer": "HINDUSTAN COCA-COLA BEVERAGES PVT. LTD.", "fssai_licence": None})
    v, _ = gemini.analyze_images(TWO, raw_response=limca)
    assert v["product_match"]["status"] == "indeterminate"


def test_a_mismatch_with_a_matching_anchor_stays_cant_tell():
    same_brand = answer(front_identity={"brand": "Maliban", "name": "Cheese Wafer", "manufacturer": None},
                        back_identity={"brand": "Maliban", "name": None, "manufacturer": None, "fssai_licence": None})
    v, _ = gemini.analyze_images(TWO, raw_response=same_brand)
    assert v["product_match"]["status"] == "indeterminate"


def test_the_scan_is_refused_even_with_the_tick():
    r = c.post("/scan", files=BOTH, data={"replay": LIVE, "pairing_confirmed": "true", "barcode": gtin()})
    assert r.status_code == 422
    j = r.json()
    assert j["reliability"]["error"] == "product_mismatch"
    assert "same pack" in j["screen"]["retake"]
    assert j["screen"]["can_send"] is False                   # two packs: nothing for a reviewer to file


def test_cant_tell_without_the_tick_says_the_front_was_not_used():
    cant_tell = answer(product_match={"status": "indeterminate", "evidence": []},
                       front_identity={"brand": "Maliban", "name": None, "manufacturer": None})
    r = c.post("/scan", files=BOTH, data={"replay": cant_tell})
    assert r.status_code == 200
    note = r.json()["screen"]["front_note"]
    assert "front" in note.lower() and "wasn't used" in note
    import test_wording
    test_wording.assert_clean([note], "front note")


def test_cant_tell_with_the_tick_uses_the_front_as_before():
    cant_tell = answer(product_match={"status": "indeterminate", "evidence": []},
                       front_identity={"brand": "Maliban", "name": None, "manufacturer": None})
    r = c.post("/scan", files=BOTH, data={"replay": cant_tell, "pairing_confirmed": "true"})
    assert r.status_code == 200 and "front_note" not in r.json()["screen"]


def test_retake_after_a_mismatch_clears_both_photos():
    app_js = open(os.path.join(main.WEB_DIR, "app.js"), encoding="utf-8").read()
    assert "product_mismatch" in app_js and "pending.front = null" in app_js

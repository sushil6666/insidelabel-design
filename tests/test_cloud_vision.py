"""
Cloud Vision as the independent reader (D-093). Google's HTTP answer is faked,
so this checks our request, parsing, cache, circuit breaker and fallback
without a network call or a cost.
"""
import io
import json
import urllib.error

import pytest

from insidelabel.extraction.providers import cloud_vision as cv
from insidelabel.extraction.providers import ocr_check

PHOTO = b"\xff\xd8 not really a jpeg, the fake API doesn't care"
LABEL = ("INGREDIENTS: Refined wheat flour, Sugar, Edible vegetable oil, "
         "Preservative (211), Emulsifier (322), Acidity regulator (503(ii)), "
         "Stabiliser (999), Net quantity 200 ml. Manufactured by Testco Foods Pvt Ltd.")
MODEL_READ = ["Refined wheat flour", "Sugar", "Edible vegetable oil", "Emulsifier (322)",
              "Acidity regulator (503(ii))"]                      # dropped the preservative


class FakeGoogle:
    def __init__(self, text=LABEL, fail=None):
        self.text, self.fail, self.calls = text, fail, []

    def __call__(self, req, timeout=None):
        self.calls.append(json.loads(req.data))
        assert req.get_header("X-goog-api-key") == "test-key"     # key in a header, not the URL
        assert "key=" not in req.full_url
        if self.fail:
            raise self.fail
        body = json.dumps({"responses": [{"fullTextAnnotation": {"text": self.text}}]}).encode()
        return io.BytesIO(body)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("GOOGLE_VISION_KEY", "test-key")
    monkeypatch.delenv("INSIDELABEL_OCR", raising=False)
    cv._CACHE.clear()
    monkeypatch.setattr(cv, "_down_until", 0.0)
    yield


def fake(monkeypatch, **kw):
    g = FakeGoogle(**kw)
    monkeypatch.setattr(cv.urllib.request, "urlopen", g)
    return g


def test_recovers_what_the_model_dropped(monkeypatch):
    g = fake(monkeypatch)
    fixed, result, recovered = ocr_check.recover_entries(PHOTO, MODEL_READ)
    assert result["reader"] == "cloud_vision" and result["missing"] == ["211"]
    assert recovered and "211" in recovered[0] and len(fixed) == len(MODEL_READ) + 1
    req = g.calls[0]["requests"][0]
    assert req["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}]
    assert req["imageContext"]["languageHints"] == ["en", "hi"]


def test_same_guards_as_tesseract(monkeypatch):
    fake(monkeypatch)
    r = ocr_check.cross_check(PHOTO, MODEL_READ)
    assert "999" in r["vote_detail"]["rejected_unknown"]           # no table row → never injected
    assert "999" not in r["missing"]
    assert "200" not in r["vote_detail"]["voted"]                  # "200 ml" is not an additive


def test_one_call_per_photo_for_every_check(monkeypatch):
    g = fake(monkeypatch)
    ocr_check.recover_entries(PHOTO, MODEL_READ)
    vision = {"back_identity": {"brand": "Testco", "name": None}, "front_identity": None}
    down, rep = ocr_check.check_identity_anchors(vision, None, PHOTO)
    assert rep["back"]["status"] == ocr_check.CORROBORATED and not down
    assert len(g.calls) == 1                                       # was up to 9 Tesseract passes


def test_failure_falls_back_to_tesseract_and_backs_off(monkeypatch):
    err = urllib.error.HTTPError(cv.ENDPOINT, 403, "Forbidden", {}, io.BytesIO(b'{"error":"billing"}'))
    g = fake(monkeypatch, fail=err)
    monkeypatch.setattr(ocr_check, "vote_ins", lambda b: ({"211"}, {"voted": ["211"]}, 6))
    monkeypatch.setattr(ocr_check, "AVAILABLE", True)
    monkeypatch.setattr(ocr_check.pytesseract, "image_to_string", lambda *a, **k: "Preservative (211)",
                        raising=False)
    r = ocr_check.cross_check(PHOTO, MODEL_READ)
    assert r["reader"] == "tesseract" and r["fallback_from"] == "cloud_vision http_403"
    assert r["missing"] == ["211"]
    ocr_check.cross_check(PHOTO, MODEL_READ)
    assert len(g.calls) == 1                                       # circuit open: no second call


def test_transient_failure_backs_off_briefly(monkeypatch):
    fake(monkeypatch, fail=urllib.error.URLError("timed out"))
    assert cv.read_text(PHOTO) is None
    assert 0 < cv._down_until - cv.time.monotonic() <= cv.DOWN_TRANSIENT_S


def test_tesseract_can_be_forced(monkeypatch):
    g = fake(monkeypatch)
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(ocr_check, "vote_ins", lambda b: (set(), {}, 6))
    monkeypatch.setattr(ocr_check, "AVAILABLE", True)
    monkeypatch.setattr(ocr_check.pytesseract, "image_to_string", lambda *a, **k: "", raising=False)
    assert ocr_check.cross_check(PHOTO, MODEL_READ)["reader"] == "tesseract"
    assert g.calls == []


def test_no_key_means_no_call(monkeypatch):
    g = fake(monkeypatch)
    monkeypatch.delenv("GOOGLE_VISION_KEY")
    assert cv.read_text(PHOTO) is None and g.calls == []


def test_a_line_break_between_class_word_and_bracket_still_counts():
    # Ziggy's back label, as Cloud Vision reads it: five numbers were lost to "\n".
    text = "Chocolate & Vanilla, Acidity Regulators\n(330, 270), Iodized Salt, Preservative\n(202), Colours"
    assert {"330", "270", "202"} <= ocr_check._ins_numbers(text)
    # …while a bracketed number after a nutrition value is still not an additive.
    assert ocr_check._ins_numbers("Saturated Fat g 7.45 17.27 g 0.03 0.77 (1100(iii), 1104) mg") == set()

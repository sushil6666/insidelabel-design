"""
D-148: the beta's daily photo-scan limit, 15 per install in any 24 hours, with
D-095's limiter. The real rules are used here with a test clock: no real time
passes and no model is called (every scan is a replay). The limit screen's words
come from lenses/screen.py and must stay true for a rolling window: they give the
time the next photo scan is free, and at that time it is.
"""
import base64
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from insidelabel import ratelimit
from insidelabel.api import main
from insidelabel.lenses import screen
from test_wording import assert_clean

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}
VISION = json.dumps({
    "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
    "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
    "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
    "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
    "ingredient_lines": ["Sugar, Salt"], "ingredient_count": 2, "ingredients": ["Sugar", "Salt"],
    "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
    "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}})

c = TestClient(main.app)
NOW = [1_000_000.0]


@pytest.fixture(autouse=True)
def test_clock(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(main.ocr_check, "AVAILABLE", False)
    monkeypatch.setattr(ratelimit.LIMITER, "rules", ratelimit.RULES)      # the real numbers
    monkeypatch.setattr(ratelimit.LIMITER, "clock", lambda: NOW[0])
    ratelimit.LIMITER.reset()
    yield
    ratelimit.LIMITER.reset()


def scan(device, **headers):
    return c.post("/scan", files=BACK, data={"replay": VISION, "device_id": device}, headers=headers)


def use_up(device):
    for i in range(ratelimit.PHOTO_SCANS_A_DAY):
        assert scan(device).status_code == 200, i
        NOW[0] += 60                                   # one a minute


def test_the_number_is_15_a_day_per_install():
    assert ratelimit.PHOTO_SCANS_A_DAY == 15
    assert ratelimit.RULES["scan"]["device"] == [(15, 86_400)]
    # D-148: barcode lookups keep their own budget, unchanged.
    assert ratelimit.RULES["lookup"] == {"device": [(120, 600)], "ip": [(600, 600)]}


def test_the_16th_photo_scan_gets_the_limit_screen(caplog):
    dev = str(uuid.uuid4())
    use_up(dev)
    with caplog.at_level(logging.WARNING, logger="insidelabel.api"):
        r = scan(dev, **{"X-Request-ID": "limit-test-1"})
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "rate_limited" and body["request_id"] == "limit-test-1"
    w = body["photo_limit"]
    assert w == screen.photo_limit(body["retry_after_s"], 15)
    assert w["title"] == "Photo scans used for now"
    assert w["text"] == "During the beta, each phone can photograph 15 packs in any 24 hours."
    assert w["barcode"] == "Scanning a barcode still works for packs we already know."
    # The first of the 15 was 15 minutes ago, so the next one is free in 23 h 45 min.
    assert body["retry_after_s"] == 86_400 - 15 * 60
    assert w["when"] == "You can photograph another pack in about 24 hours."
    assert int(r.headers["Retry-After"]) == body["retry_after_s"]
    assert "Photo scans used for now." in body["detail"]               # older apps show this
    assert any("rate limited: scan" in m for m in caplog.messages)       # logged, not stored


def test_a_barcode_lookup_still_works_after_the_limit():
    dev = str(uuid.uuid4())
    use_up(dev)
    assert scan(dev).status_code == 429
    r = c.post("/scan", data={"barcode": "8901000000019", "device_id": dev})
    assert r.status_code == 404 and r.json()["error"] == "not_in_catalogue"   # looked up, not refused


def test_the_limit_resets_when_the_words_say():
    dev = str(uuid.uuid4())
    use_up(dev)
    first = scan(dev).json()
    NOW[0] += 12 * 3600
    half = scan(dev).json()
    assert half["photo_limit"]["when"] == "You can photograph another pack in about 12 hours."
    NOW[0] += half["retry_after_s"] - 1
    assert scan(dev).status_code == 429                                  # a second early: still refused
    NOW[0] += 1
    assert scan(dev).status_code == 200                                  # on time: one more is free
    assert scan(dev).status_code == 429                                  # the next leaves a minute later
    assert first["retry_after_s"] > half["retry_after_s"]


def test_another_phone_is_not_affected():
    use_up(str(uuid.uuid4()))
    assert scan(str(uuid.uuid4())).status_code == 200


def test_a_refusal_by_the_ip_rule_is_not_the_limit_screen(monkeypatch):
    # Only the install's daily rule shows "you've used your photo scans"; anything
    # else would make that sentence untrue.
    monkeypatch.setattr(ratelimit.LIMITER, "rules", {
        "scan": {"device": ratelimit.RULES["scan"]["device"], "ip": [(2, 600)]}})
    for _ in range(2):
        assert scan(str(uuid.uuid4())).status_code == 200
    body = scan(str(uuid.uuid4())).json()
    assert body["error"] == "rate_limited" and "photo_limit" not in body


@pytest.mark.parametrize("seconds,when", [
    (1, "about 1 minute"), (59, "about 1 minute"), (61, "about 2 minutes"),
    (89 * 60, "about 89 minutes"), (90 * 60, "about 2 hours"), (5 * 3600 + 10, "about 5 hours"),
    (86_400, "about 24 hours"),
])
def test_when_words(seconds, when):
    assert screen.photo_limit(seconds, 15)["when"] == f"You can photograph another pack in {when}."


def test_limit_words_are_clean():
    w = screen.photo_limit(3600, 15)
    assert_clean(list(w.values()), "photo limit screen")
    assert not any(word in " ".join(w.values()).lower() for word in ("pro", "upgrade", "subscri", "pay"))

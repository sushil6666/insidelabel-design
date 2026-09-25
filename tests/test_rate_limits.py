"""
Rate limits on /scan and /problem, per install and per IP (D-095).

A scan with photos is a paid model call, so a runaway client (or anyone with
the URL) could spend the Gemini credit in minutes. The limits are checked
before a photo is read or a model is called. Rules are shrunk here so each
test trips them in a few requests; nothing here calls a real model.
"""
import base64
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from insidelabel import ratelimit
from insidelabel.api import main

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


@pytest.fixture(autouse=True)
def small_rules(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(main.ocr_check, "AVAILABLE", False)       # no OCR needed for these
    monkeypatch.setattr(ratelimit.LIMITER, "rules", {
        "scan": {"device": [(3, 600)], "ip": [(5, 600)]},
        "lookup": {"device": [(4, 600)], "ip": [(6, 600)]},
        "problem": {"device": [(2, 3600)], "ip": [(3, 3600)]},
    })
    ratelimit.LIMITER.reset()
    yield
    ratelimit.LIMITER.reset()


def scan(device=None, headers=None, **data):
    if device:
        data["device_id"] = device
    return c.post("/scan", files=BACK, data={"replay": VISION, **data}, headers=headers or {})


# ---------------------------------------------------------------- the limiter itself

def test_sliding_window_allows_then_refuses_then_recovers():
    now = [1000.0]
    lim = ratelimit.Limiter({"x": {"device": [(2, 60)]}}, clock=lambda: now[0])
    assert lim.hit("x", device="a") is None
    now[0] += 10
    assert lim.hit("x", device="a") is None
    wait = lim.hit("x", device="a")
    assert wait == pytest.approx(50, abs=1)             # the first hit leaves the window at t=60
    assert lim.hit("x", device="b") is None             # another install is unaffected
    now[0] += 51
    assert lim.hit("x", device="a") is None


def test_every_rule_must_pass_and_a_refusal_costs_nothing():
    now = [0.0]
    lim = ratelimit.Limiter({"x": {"device": [(5, 60), (6, 3600)]}}, clock=lambda: now[0])
    for i in range(5):
        assert lim.hit("x", device="a") is None
    assert lim.hit("x", device="a") is not None         # 10-minute rule
    now[0] += 61
    assert lim.hit("x", device="a") is None             # 6th of the hour
    assert lim.hit("x", device="a") > 3000              # hourly rule; the refused try wasn't counted


def test_a_refused_request_does_not_count_against_the_other_key():
    # Device over its limit: the IP's count must not grow from its refused tries.
    lim = ratelimit.Limiter({"x": {"device": [(1, 60)], "ip": [(3, 60)]}}, clock=lambda: 0.0)
    assert lim.hit("x", device="a", ip="1.2.3.4") is None
    for _ in range(5):
        assert lim.hit("x", device="a", ip="1.2.3.4") is not None
    assert lim.hit("x", device="b", ip="1.2.3.4") is None
    assert lim.hit("x", device="c", ip="1.2.3.4") is None


def test_memory_is_bounded():
    lim = ratelimit.Limiter({"x": {"ip": [(1, 60)]}}, clock=lambda: 0.0, max_keys=100)
    for i in range(1000):
        lim.hit("x", ip=f"10.0.{i // 256}.{i % 256}")
    assert len(lim._hits) <= 100


# ---------------------------------------------------------------- /scan

def test_scan_is_limited_per_install():
    dev = str(uuid.uuid4())
    for _ in range(3):
        assert scan(dev).status_code == 200
    r = scan(dev, headers={"X-Request-ID": "rl-test-1"})
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "rate_limited" and body["retryable"] is True
    assert body["request_id"] == "rl-test-1" and body["retry_after_s"] > 0
    assert int(r.headers["Retry-After"]) == body["retry_after_s"]
    assert scan(str(uuid.uuid4())).status_code == 200      # another phone on the same IP is fine


def test_scan_is_limited_per_ip_whatever_the_device_id():
    for _ in range(5):
        assert scan(str(uuid.uuid4())).status_code == 200
    assert scan(str(uuid.uuid4())).status_code == 429       # a new device id each time doesn't help
    assert scan().status_code == 429                         # nor does sending none


def test_a_refused_scan_never_reaches_the_model(monkeypatch):
    dev = str(uuid.uuid4())
    for _ in range(3):
        scan(dev)

    def no_model(*a, **k):
        raise AssertionError("model called on a rate-limited scan")
    monkeypatch.setattr(main.gemini, "analyze_images", no_model)
    assert scan(dev).status_code == 429


def test_barcode_lookups_have_their_own_budget():
    # A lookup costs ~nothing; a parent checking a shelf by barcode must not use
    # up the photo-scan budget, and the other way round.
    dev = str(uuid.uuid4())
    for _ in range(3):
        assert scan(dev).status_code == 200
    assert c.post("/scan", data={"barcode": "8901000000013", "device_id": dev}).status_code == 404
    for _ in range(3):
        c.post("/scan", data={"barcode": "8901000000013", "device_id": dev})
    r = c.post("/scan", data={"barcode": "8901000000013", "device_id": dev})
    assert r.status_code == 429


def test_forwarded_for_is_trusted_only_behind_a_configured_proxy(monkeypatch):
    for i in range(5):
        scan(str(uuid.uuid4()), headers={"X-Forwarded-For": f"203.0.113.{i}"})
    # Not configured: the header is ignored, so all five came from one address.
    assert scan(str(uuid.uuid4()), headers={"X-Forwarded-For": "203.0.113.99"}).status_code == 429
    ratelimit.LIMITER.reset()
    monkeypatch.setenv("INSIDELABEL_PROXY_HOPS", "1")
    for i in range(6):
        # The proxy appends the real client last; anything to its left is the client's own claim.
        h = {"X-Forwarded-For": f"198.51.100.7, 203.0.113.{i}"}
        assert scan(str(uuid.uuid4()), headers=h).status_code == 200
    h = {"X-Forwarded-For": "198.51.100.7, 203.0.113.0"}
    for _ in range(4):
        scan(str(uuid.uuid4()), headers=h)
    assert scan(str(uuid.uuid4()), headers=h).status_code == 429


def test_the_limit_messages_pass_the_wording_lint():
    import test_wording
    dev = str(uuid.uuid4())
    for _ in range(4):
        r = scan(dev)
    assert "minute" in r.json()["detail"]
    test_wording.assert_clean([r.json()["detail"], ratelimit.PROBLEM_TEXT, ratelimit.SEND_TEXT], "429 bodies")


# ---------------------------------------------------------------- /problem

def test_problem_reports_are_limited_per_install_and_ip():
    dev = str(uuid.uuid4())
    body = {"kind": "user", "device_id": dev, "events": []}
    # Without a database /problem answers 503, but a flood is still refused first.
    assert [c.post("/problem", json=body).status_code for _ in range(3)] == [503, 503, 429]
    other = {"kind": "auto", "device_id": str(uuid.uuid4()), "events": []}
    assert c.post("/problem", json=other).status_code == 503
    assert c.post("/problem", json={**other, "device_id": str(uuid.uuid4())}).status_code == 429   # IP: 3/hour

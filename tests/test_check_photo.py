"""
Every upload is checked as soon as it's picked (D-104): the app shows a green
tick or a red cross with the reason, before the user taps "Check this pack".
Barcodes come from the camera or from a photo, read on the server; typing one
isn't offered (a wrong number files a pack under someone else's product).

No model call happens here and nothing is stored.
"""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import zxingcpp

from insidelabel import barcode
from insidelabel.api import main

c = TestClient(main.app)


def gtin(body):
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def barcode_photo(*codes, size=(1200, 900), fmt=zxingcpp.BarcodeFormat.EAN13, noise=True):
    """A photo with the given barcodes printed on it, as a JPEG."""
    canvas = Image.effect_noise(size, 25).convert("L") if noise else Image.new("L", size, 230)
    canvas = canvas.point(lambda v: 150 + v // 3)          # light background, like a pack
    for i, code in enumerate(codes):
        img = zxingcpp.create_barcode(code, fmt).to_image(scale=4)
        h, w = img.shape[:2]
        canvas.paste(Image.frombytes("L", (w, h), bytes(memoryview(img))), (60 + i * 560, 300))
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def label_photo(w=1200, h=900):
    buf = io.BytesIO()
    Image.effect_noise((w, h), 60).convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


def check(role, data, mime="image/jpeg"):
    return c.post("/check-photo", data={"role": role}, files={"photo": (f"{role}.jpg", data, mime)})


def no_model(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the model was called")
    monkeypatch.setattr(main.gemini, "analyze_images", refuse)


# ---------------------------------------------------------------- reading barcodes from photos

def test_a_barcode_photo_gets_a_green_tick(monkeypatch):
    no_model(monkeypatch)
    code = gtin("890106301032")
    r = check("barcode", barcode_photo(code))
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["barcode"] == code
    assert code in j["message"]


def test_upc_codes_are_stored_one_way():
    # The phone camera reports a UPC-A as 12 digits, the photo reader as 13
    # (leading 0). One pack must have one catalogue key.
    upc = gtin("01234567890")
    assert barcode.check(upc) == ("0" + upc, None)
    assert barcode.check("0" + upc) == ("0" + upc, None)
    j = check("barcode", barcode_photo(upc, fmt=zxingcpp.BarcodeFormat.UPCA)).json()
    assert j["ok"] is True and j["barcode"] == "0" + upc


def test_upc_e_is_expanded():
    j = check("barcode", barcode_photo("04252614", fmt=zxingcpp.BarcodeFormat.UPCE)).json()
    assert j["ok"] is True and j["barcode"] == "0042100005264"


def test_no_barcode_in_the_photo_gets_a_red_cross():
    j = check("barcode", label_photo()).json()
    assert j["ok"] is False and j["problem"] == "no_barcode"
    assert "barcode" in j["message"].lower()


def test_a_barcode_that_is_not_a_retail_pack_gets_a_red_cross_with_the_reason():
    j = check("barcode", barcode_photo(gtin("978014300723"))).json()     # a book
    assert j["ok"] is False and j["problem"] == "not_a_product"
    assert j["message"] == barcode.MESSAGES["not_a_product"]


def test_two_different_barcodes_are_not_guessed_between():
    j = check("barcode", barcode_photo(gtin("890106301032"), gtin("890106301049"))).json()
    assert j["ok"] is False and j["problem"] == "several_barcodes"


def test_a_back_photo_gets_a_tick_and_any_barcode_on_it():
    code = gtin("890603201881")
    j = check("back", barcode_photo(code)).json()
    assert j["ok"] is True and j["barcode"] == code
    j = check("back", label_photo()).json()
    assert j["ok"] is True and j["barcode"] is None
    assert "Check this pack" in j["message"]


@pytest.mark.parametrize("role, data, problem", [
    ("back", b"%PDF-1.7 not a photo", "not_an_image"),
    ("back", label_photo(300, 200), "photo_too_small"),
    ("front", label_photo(300, 200), "photo_too_small"),
])
def test_a_bad_file_gets_a_red_cross(role, data, problem):
    j = check(role, data).json()
    assert j["ok"] is False and j["problem"] == problem and role in j["message"]


def test_a_small_barcode_crop_is_fine():
    # A close-up of just the barcode is smaller than a label photo needs to be.
    j = check("barcode", barcode_photo(gtin("890106301032"), size=(620, 360), noise=False)).json()
    assert j["ok"] is True


def test_bad_role_and_missing_photo():
    assert check("selfie", label_photo()).status_code == 422
    assert c.post("/check-photo", data={"role": "back"}).status_code == 422


def test_checking_is_rate_limited(monkeypatch):
    from insidelabel import ratelimit
    monkeypatch.setattr(ratelimit.LIMITER, "rules", {**ratelimit.RULES, "check_photo": {"ip": [(2, 600)]}})
    assert [check("back", label_photo()).status_code for _ in range(3)] == [200, 200, 429]


def test_checking_needs_an_invite_when_the_beta_is_closed(monkeypatch):
    monkeypatch.setattr(main, "INVITE_ONLY", True)
    monkeypatch.setattr(main, "STORE", None)
    assert check("back", label_photo()).status_code == 503


def test_every_message_passes_the_wording_lint():
    import test_wording
    test_wording.assert_clean(list(main.CHECK_MESSAGES.values()), "check-photo messages")


# ---------------------------------------------------------------- where the barcode came from

def test_the_scan_records_where_the_barcode_came_from(monkeypatch):
    seen = {}
    real = main._persist

    def spy(fn, *a, **kw):
        if kw.get("trace"):
            seen.update(kw["trace"]["request"])
        return real(fn, *a, **kw)
    monkeypatch.setattr(main, "_persist", spy)
    monkeypatch.setattr(main, "STORE", type("S", (), {"find_current": lambda self, b: None})())
    r = c.post("/scan", data={"barcode": gtin("890106301032"), "barcode_source": "photo"})
    assert r.status_code == 404
    r = c.post("/scan", data={"barcode": gtin("890106301032"), "barcode_source": "typed"})
    assert r.status_code == 422 and r.json()["error"] == "bad_barcode_source"


# ---------------------------------------------------------------- the app

def test_the_app_offers_no_typed_barcode():
    import os
    web = main.WEB_DIR
    app_js = open(os.path.join(web, "app.js"), encoding="utf-8").read()
    assert "manualEntry" not in app_js and 'inputmode: "numeric"' not in app_js
    assert "No barcode? Photograph the ingredients" in app_js
    assert "/check-photo" in open(os.path.join(web, "lib.js"), encoding="utf-8").read()

"""
Only real packs get in (D-103): a barcode must be a retail product's GTIN, a
photo must be a readable picture, and what it shows must be a food pack, not a
screen or anything else. The first two are checked before any paid model
call; the third is the model reading, and the rules deciding (D-004).

Found on 2026-09-26: a scan with barcode 12222333333333 and two screenshots of
database software cost a Gemini read, came back as "retake the photo", and
counted towards "Send it to us".
"""
import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from insidelabel import barcode
from insidelabel.api import main
from insidelabel.extraction.providers import gemini, prompt

c = TestClient(main.app)


def gtin(body):
    """body + its GS1 check digit (GS1 General Specifications 7.9.1)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def photo(w=1200, h=900, blank=False, fmt="JPEG"):
    im = Image.new("L", (w, h), 20) if blank else Image.effect_noise((w, h), 60).convert("L")
    buf = io.BytesIO()
    im.convert("RGB").save(buf, fmt)
    return buf.getvalue()


def vision(**kw):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": None},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": ["Sugar, Salt"], "ingredient_count": 2, "ingredients": ["Sugar", "Salt"],
         "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(autouse=True)
def no_ocr(monkeypatch):
    monkeypatch.setenv("INSIDELABEL_OCR", "tesseract")
    monkeypatch.setattr(main.ocr_check, "AVAILABLE", False)


def no_model(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the model was called")
    monkeypatch.setattr(main.gemini, "analyze_images", refuse)


# ---------------------------------------------------------------- barcodes (GS1 General Specifications 26.0)

@pytest.mark.parametrize("code, reason", [
    ("12222333333333", "case_code"),                    # the 2026-09-26 scan: GTIN-14, indicator 1
    (gtin("9890106301032"), "case_code"),               # indicator 9: variable-measure trade item
    (gtin("222233333333"), "store_code"),               # GS1 Prefix 20-29: in-store, weighed items
    (gtin("020000000001"), "store_code"),               # GS1 Prefix 02
    (gtin("040000000001"), "store_code"),               # GS1 Prefix 04: within a company
    (gtin("2000001"), "store_code"),                    # GS1-8 prefix 200-299
    (gtin("000000000001"), "store_code"),               # 0000000: within a company
    (gtin("978014300723"), "not_a_product"),            # ISBN: a book
    (gtin("977123456700"), "not_a_product"),            # ISSN: a magazine
    (gtin("981000000001"), "not_a_product"),            # coupon
    (gtin("990000000001"), "not_a_product"),            # coupon
    (gtin("980000000001"), "not_a_product"),            # refund receipt
    (gtin("952000000001"), "not_a_product"),            # GS1 demonstration number
    (gtin("985000000001"), "not_a_product"),            # reserved
    (gtin("890106301032")[:-1] + str((int(gtin("890106301032")[-1]) + 1) % 10), "check_digit"),
    ("123", "length"),
])
def test_codes_that_are_not_a_retail_pack(code, reason):
    got, why = barcode.check(code)
    assert got is None and why == reason, (code, why)


@pytest.mark.parametrize("code, normal", [
    (gtin("890106301032"), None),                       # GS1 India
    (gtin("500015940402"), None),                       # GS1 UK
    (gtin("01234567890"), "0" + gtin("01234567890")),  # UPC-A, stored as its GTIN-13 (D-104)
    ("0" + gtin("890106301032"), gtin("890106301032")),  # GTIN-14 with indicator 0 = the GTIN-13 inside
    (gtin("5012345"), None),                            # GTIN-8
])
def test_retail_codes_pass(code, normal):
    assert barcode.check(code) == (normal or code, None)


def test_scan_refuses_a_bad_barcode_before_anything_else(monkeypatch):
    no_model(monkeypatch)
    r = c.post("/scan", data={"barcode": "12222333333333"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "bad_barcode" and body["reason"] == "case_code"
    assert "carton" in body["detail"] or "case" in body["detail"]


def test_scan_looks_up_the_gtin13_inside_a_gtin14():
    r = c.post("/scan", data={"barcode": "0" + gtin("890106301032")})
    assert r.status_code == 404 and r.json()["error"] == "not_in_catalogue"   # looked up, not refused


def test_every_barcode_message_passes_the_wording_lint():
    import test_wording
    assert_clean = test_wording.assert_clean
    assert_clean(list(barcode.MESSAGES.values()), "barcode messages")


# ---------------------------------------------------------------- photo files, before the model

def test_a_file_that_is_not_an_image_never_reaches_the_model(monkeypatch):
    no_model(monkeypatch)
    r = c.post("/scan", files={"back": ("b.jpg", b"%PDF-1.7 not a photo", "image/jpeg")})
    assert r.status_code == 415 and r.json()["error"] == "not_an_image"


def test_a_tiny_photo_is_refused(monkeypatch):
    no_model(monkeypatch)
    r = c.post("/scan", files={"back": ("b.jpg", photo(400, 200), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == "photo_too_small"


def test_a_blank_or_black_photo_is_refused(monkeypatch):
    no_model(monkeypatch)
    r = c.post("/scan", files={"back": ("b.jpg", photo(blank=True), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == "photo_blank"


def test_a_bad_front_is_refused_too(monkeypatch):
    no_model(monkeypatch)
    r = c.post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg"),
                               "front": ("f.jpg", photo(100, 100), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == "photo_too_small" and "front" in r.json()["detail"]


def test_a_good_photo_reaches_the_model(monkeypatch):
    called = []
    real = gemini.analyze_images

    def fake(images, raw_response=None, **kw):
        called.append(len(images))
        return real(images, raw_response=vision(image_content={"back": "food_pack",
                                                                                "front": "not_provided"}))
    monkeypatch.setattr(main.gemini, "analyze_images", fake)
    r = c.post("/scan", files={"back": ("b.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200 and called == [1]


# ---------------------------------------------------------------- what the photo shows (the model reads, rules decide)

def test_the_model_is_asked_what_each_photo_shows():
    schema = prompt.VISION_RESPONSE_SCHEMA
    ic = schema["properties"]["image_content"]["properties"]
    assert set(ic["back"]["enum"]) == {"food_pack", "screen", "not_food", "not_provided"}
    assert "image_content" in schema["required"]                  # Gemini must answer it
    assert "image_content" not in gemini.REQUIRED_KEYS            # answers recorded before D-103 still parse


@pytest.mark.parametrize("seen, error, words", [
    ("not_food", "not_a_food_pack", "food"),
])
def test_a_back_photo_that_is_not_a_pack_is_refused_plainly(seen, error, words):
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png")},
               data={"replay": vision(back_status="not_provided", ingredients_status="not_found",
                                      ingredients=[], image_content={"back": seen, "front": "not_provided"})})
    assert r.status_code == 422
    body = r.json()
    assert body["reliability"]["error"] == error
    assert words in body["screen"]["retake"].lower()
    assert body["screen"]["can_send"] is False                  # not "Send it to us" material


def test_a_readable_list_on_a_screen_is_read_and_marked():
    # D-130 (amends D-103): read, marked "from a screen"; never catalogued (tests/test_screen_read.py).
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png")},
               data={"replay": vision(image_content={"back": "screen", "front": "not_provided"})})
    assert r.status_code == 200 and r.json()["reliability"]["from_screen"] is True
    assert r.json()["screen"]["from_screen"]["title"] == "Read from a screen, not the pack."


def test_an_ordinary_refusal_can_still_be_sent_to_us():
    from gtins import gtin
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png")},
               data={"barcode": gtin(), "replay": vision(back_status="unreadable", ingredients_status="unreadable", ingredients=[],
                                      image_content={"back": "food_pack", "front": "not_provided"})})
    assert r.status_code == 422 and r.json()["screen"]["can_send"] is True


def test_a_front_that_is_not_a_pack_is_dropped_not_fatal():
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png"),
                               "front": ("f.png", photo(fmt="PNG"), "image/png")},
               data={"pairing_confirmed": "true",
                     "replay": vision(front_status="read", front_claims=["No added sugar"],
                                      product_match={"status": "indeterminate", "evidence": []},
                                      image_content={"back": "food_pack", "front": "not_food"})})
    assert r.status_code == 200
    j = r.json()
    assert j["extracted"]["front_claims"] == []
    assert any(cv["code"] == "front_not_a_pack" for cv in j["reliability"]["caveats"])


def test_an_answer_recorded_before_d103_still_works():
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png")}, data={"replay": vision()})
    assert r.status_code == 200


def test_refusal_texts_pass_the_wording_lint():
    import test_wording
    from insidelabel.lenses import screen
    test_wording.assert_clean([screen.RETAKE[k] for k in ("back_is_a_screen", "not_a_food_pack")]
                              + list(screen.HEADLINE.values()), "not-a-pack texts")


def test_the_smallest_gold_photos_pass():
    # Gemini read these correctly; the size floor must never refuse them.
    import glob
    import os
    from insidelabel import photo_check
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shots = glob.glob(os.path.join(root, "photos", "*"))
    if not shots:
        pytest.skip("no gold photos in this checkout")
    for p in shots:
        mime = "image/png" if p.endswith(".png") else "image/jpeg"
        assert photo_check.check(open(p, "rb").read(), mime, "back") is None, p


def test_a_single_photo_described_under_the_other_role_still_counts():
    # Gemini's real answer for a dbt screenshot sent alone (2026-09-26 live check):
    # it isn't told which role the image has, and put its description under front.
    r = c.post("/scan", files={"back": ("b.png", photo(fmt="PNG"), "image/png")},
               data={"replay": vision(back_status="not_provided", ingredients_status="not_found", ingredients=[],
                                      image_content={"back": "not_provided", "front": "not_food"})})
    assert r.status_code == 422 and r.json()["reliability"]["error"] == "not_a_food_pack"
    assert r.json()["screen"]["can_send"] is False

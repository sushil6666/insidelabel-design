"""
D-170 (Sushil, 2026-10-07, "Accept, no hint line"): a photo the server can't use is shown
back to the user with its problem named in a short label, then the fix line (the RETAKE
sentence, unchanged). A tester asked to be told what went wrong.

Every code the server can refuse a photo with has a label: the refusals in gates.py, the
D-118 second-reader refusal, the photo check's codes (photo_check.py, /check-photo's
CHECK_MESSAGES) and a barcode photo's (barcode.MESSAGES). Words live in lenses/screen.py.
"""
import io
import json
import os
import re
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from test_recipe_gate import SAFFOLA_RECIPE, reading
from test_wording import assert_clean

from insidelabel import barcode, photo_check
from insidelabel.api import main
from insidelabel.lenses import screen
from insidelabel.reliability import gates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = open(os.path.join(ROOT, "src", "insidelabel", "reliability", "gates.py"), encoding="utf-8").read()


def refusal_codes():
    """Every code a refused scan or a turned-down photo can carry."""
    codes = set(re.findall(r'"error": "(\w+)"', GATES)) | set(gates._REFUSE.values()) | set(gates.NOT_A_PACK)
    codes |= {"independent_read_failed", "partial", "recipe", "screen_unread"}     # D-118, D-066, D-166, D-130
    codes |= set(photo_check.MESSAGES) | set(barcode.MESSAGES)
    codes |= {k for k in main.CHECK_MESSAGES if not k.endswith(("_ok", "_too"))}
    return codes


def test_every_refusal_code_has_a_label():
    codes = refusal_codes()
    assert {"ingredient_list_unreadable", "no_ingredient_list_found", "back_not_read", "not_a_food_pack",
            "product_mismatch", "photo_too_small", "photo_blank", "no_barcode", "barcode_unsure"} <= codes
    missing = codes - set(screen.PROBLEM_LABEL)
    assert not missing, missing
    for code in codes:
        p = screen.problem(code, "fix")
        assert p == {"code": code, "label": screen.PROBLEM_LABEL[code], "fix": "fix"}
    assert screen.problem("something_new", "fix")["label"] == "We couldn't read this label"


def test_labels_are_short_and_pass_the_wording_lint():
    for code, label in screen.PROBLEM_LABEL.items():
        assert len(label) <= 45 and not label.endswith("."), code
        assert_clean(label, code)


def scan(raw, **files):
    files = files or {"back": ("b.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes, "image/jpeg")}
    r = TestClient(main.app).post("/scan", files=files, data={"replay": json.dumps(raw)})
    return r, r.json().get("screen") or {}


def test_each_refusal_names_its_problem_and_keeps_its_fix_line():
    cases = [
        (dict(ingredients_status="unreadable"), "ingredient_list_unreadable", "Too blurred or dark to read"),
        (dict(ingredients_status="not_found"), "no_ingredient_list_found", "No ingredient list in this photo"),
        (dict(back_status="unreadable"), "back_not_read", "No ingredient list in this photo"),
        (dict(image_content={"back": "not_food"}), "not_a_food_pack", "Not a food pack"),
    ]
    for change, code, label in cases:
        raw = {**reading(["Wheat flour", "Sugar"]), **change}
        r, s = scan(raw)
        assert r.status_code == 422, (code, r.text)
        assert s["state"] == "retake" and s["problem"] == {"code": code, "label": label, "fix": s["retake"]}, code
    r, s = scan(reading(SAFFOLA_RECIPE))                                               # D-166
    assert s["problem"]["label"] == "This is a recipe, not the pack's list"
    assert s["problem"]["fix"] == s["retake"] == screen.RETAKE_RECIPE


def test_different_packs_name_the_pair():
    raw = {**reading(["Wheat flour", "Sugar"]), "front_status": "read",
           "product_match": {"status": "mismatch", "evidence": ["front says Limca, back says a different brand"]}}
    photo = ("f.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes, "image/jpeg")
    r, s = scan(raw, back=photo, front=("g.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes, "image/jpeg"))
    assert r.status_code == 422, r.text
    assert s["problem"]["code"] == "product_mismatch"
    assert s["problem"]["label"] == "Front and back look like different packs"


def test_a_screen_we_could_not_read_says_so():
    r, s = scan({**reading([]), "ingredients_status": "not_found", "image_content": {"back": "screen"}})
    assert r.status_code == 422, r.text
    assert s["problem"] == {"code": "screen_unread", "label": "No list we can read on this screen",
                            "fix": screen.SCREEN_RETAKE}


def test_a_partial_read_names_the_cut_and_a_full_read_has_no_problem():
    r, s = scan({**reading(["Wheat flour", "Sugar", "Milk solids"]), "ingredients_status": "partial"})
    assert r.status_code == 200, r.text
    assert s["problem"] == {"code": "partial", "label": "Part of the list is cut off", "fix": screen.RETAKE_PARTIAL}
    r, s = scan(reading(["Wheat flour", "Sugar", "Milk solids"]))
    assert r.status_code == 200 and "problem" not in s and s["retake"] is None


def _jpeg(size, colour=(20, 20, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "JPEG")
    return buf.getvalue()


def test_the_photo_check_names_its_problem():
    c = TestClient(main.app)
    small = c.post("/check-photo", data={"role": "back"}, files={"photo": ("s.jpg", _jpeg((200, 150)), "image/jpeg")})
    assert small.json()["ok"] is False and small.json()["label"] == "Too small"
    assert small.json()["message"] == photo_check.MESSAGES["photo_too_small"].format(role="back")
    blank = c.post("/check-photo", data={"role": "back"}, files={"photo": ("d.jpg", _jpeg((1600, 1200)), "image/jpeg")})
    assert blank.json()["problem"] == "photo_blank" and blank.json()["label"] == "Too dark or blank"
    none = c.post("/check-photo", data={"role": "barcode"},
                  files={"photo": ("n.jpg", _jpeg((800, 600)), "image/jpeg")})
    assert none.json()["label"] in ("No barcode found", "Too dark or blank")


def test_scan_refuses_a_blank_photo_with_its_label():
    r = TestClient(main.app).post("/scan", files={"back": ("d.jpg", _jpeg((1600, 1200)), "image/jpeg")})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "photo_blank" and r.json()["label"] == "Too dark or blank"

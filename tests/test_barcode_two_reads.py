"""
D-144 (RECOMMENDED, replacing D-141): a barcode read from a photo counts when two
zxing-cpp reads agree (the photo up to 2400 px, then at three-quarter size), or when
its digits are printed in that photo's OCR text (the D-093 second reading: /scan has
it for the back photo, /check-photo has none). Otherwise it is refused, never guessed.

The cases: Sushil's phone check (2026-09-30), a small, blurry barcode photo read as
0961676012608 where the pack prints 8901058018608; and 0921129008343, a misread of the
Corn Flakes pack that prints 8901499008343. Each passes barcode.check() (the check
digit catches one wrong digit, not several). D-141 alone (two reads) refused correct
codes on the server: half size 2 of 6, three-quarter size 1 of 6 (a second read found
nothing where the first matched the camera read); the OCR text is what keeps those.
zxing-cpp is stood in for in most tests: the n-th read of a photo gives answers[n].
"""
import io
import os
import sys

import zxingcpp
from fastapi.testclient import TestClient
from test_check_photo import barcode_photo

from insidelabel import barcode
from insidelabel.api import main

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import barcode_reads  # noqa: E402

MISREAD, PRINTED = "0961676012608", "8901058018608"
c = TestClient(main.app)


class _Read:
    def __init__(self, text):
        self.text, self.format = text, zxingcpp.BarcodeFormat.EAN13


def reads(monkeypatch, *answers):
    """zxing-cpp stood in for: the n-th call returns answers[n] (None: nothing found)."""
    calls = []

    def fake(image, formats=None, **kw):
        n = len(calls)
        calls.append(n)
        text = answers[n] if n < len(answers) else answers[-1]
        return [_Read(text)] if text else []
    monkeypatch.setattr(zxingcpp, "read_barcodes", fake)
    return calls


def check_barcode(role="barcode"):
    return c.post("/check-photo", data={"role": role},
                  files={"photo": ("barcode.jpg", barcode_photo(PRINTED), "image/jpeg")}).json()


OTHER_MISREAD, CORN_FLAKES = "0921129008343", "8901499008343"
CORN_FLAKES_OCR = "INGREDIENTS: Corn grits, Sugar, Salt.\nNet wt 250 g\n8 901499 008343"


def test_both_numbers_pass_the_gs1_check_which_is_why_a_second_read_is_needed():
    assert barcode.check(MISREAD) == (MISREAD, None) and barcode.check(PRINTED) == (PRINTED, None)
    assert sum(a != b for a, b in zip(MISREAD, PRINTED)) == 6
    assert barcode.check(OTHER_MISREAD) == (OTHER_MISREAD, None)


# ---------------------------------------------------------------- /check-photo: two reads, no OCR text

def test_two_reads_that_agree_are_accepted(monkeypatch):
    reads(monkeypatch, PRINTED, PRINTED)
    j = check_barcode()
    assert j["ok"] and j["barcode"] == PRINTED


def test_sushils_case_two_reads_that_disagree_are_refused(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    j = check_barcode()
    assert not j["ok"] and j["barcode"] is None and j["problem"] == "barcode_unsure"


def test_a_second_read_that_finds_nothing_is_refused(monkeypatch):
    reads(monkeypatch, MISREAD, None)
    j = check_barcode()
    assert not j["ok"] and j["barcode"] is None and j["problem"] == "barcode_unsure"


def test_the_refusal_points_to_the_camera_scanner(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    assert check_barcode()["message"] == barcode.MESSAGES["barcode_unsure"]
    assert barcode.MESSAGES["barcode_unsure"].split(". ")[1].startswith("Scan it with the camera scanner")


def test_a_barcode_on_a_back_photo_follows_the_same_rule(monkeypatch):
    # "Barcode ... found on it too" only when both reads agree; the back photo itself is still fine.
    reads(monkeypatch, MISREAD, PRINTED)
    j = check_barcode("back")
    assert j["ok"] and j["barcode"] is None and MISREAD not in j["message"]
    reads(monkeypatch, PRINTED, PRINTED)
    assert check_barcode("back")["barcode"] == PRINTED


def test_no_second_read_when_the_first_finds_nothing(monkeypatch):
    calls = reads(monkeypatch, None)
    assert check_barcode()["problem"] == "no_barcode" and len(calls) == 1


def test_the_old_rule_is_kept_for_the_measurement(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    assert barcode.read_from_photo(barcode_photo(PRINTED), two_reads=False) == ([MISREAD], [])


# ---------------------------------------------------------------- the OCR text (at /scan)

def test_a_correct_code_in_the_ocr_text_is_accepted_when_the_second_read_is_empty(monkeypatch):
    calls = reads(monkeypatch, CORN_FLAKES, None)
    assert barcode.read_from_photo(barcode_photo(CORN_FLAKES), ocr_text=CORN_FLAKES_OCR) == ([CORN_FLAKES], [])
    assert len(calls) == 1                     # the OCR text showed it: no second read needed


def test_0921129008343_is_refused_when_the_ocr_text_shows_the_printed_code(monkeypatch):
    reads(monkeypatch, OTHER_MISREAD, None)
    assert barcode.read_from_photo(barcode_photo(CORN_FLAKES), ocr_text=CORN_FLAKES_OCR) == ([], ["barcode_unsure"])


def test_0961676012608_is_refused_with_or_without_ocr_text(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    assert barcode.read_from_photo(barcode_photo(PRINTED)) == ([], ["barcode_unsure"])
    reads(monkeypatch, MISREAD, PRINTED)
    assert barcode.read_from_photo(barcode_photo(PRINTED), ocr_text="8 901058 018608") == ([], ["barcode_unsure"])


def test_photo_code_takes_the_one_code_that_counts(monkeypatch):
    reads(monkeypatch, CORN_FLAKES, None)
    got = barcode.photo_code([("back", barcode_photo(CORN_FLAKES))], CORN_FLAKES_OCR)
    assert got["code"] == CORN_FLAKES and got["status"] == "found"
    reads(monkeypatch, OTHER_MISREAD, None)
    got = barcode.photo_code([("back", barcode_photo(CORN_FLAKES))], CORN_FLAKES_OCR)
    assert got["code"] is None and got["status"] == "unsure" and got["unsure"] == ["back"]
    # the OCR text is the back's: a front photo is two reads only
    reads(monkeypatch, CORN_FLAKES, None)
    assert barcode.photo_code([("front", barcode_photo(CORN_FLAKES))], CORN_FLAKES_OCR)["code"] is None


# ---------------------------------------------------------------- the measurement

def test_the_measuring_tool_counts_what_the_new_rule_would_refuse(monkeypatch, tmp_path):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (tmp_path / name).write_bytes(barcode_photo(PRINTED))
    # Per photo: the old read, then two reads; c.jpg has OCR text, so a third read with it.
    reads(monkeypatch, MISREAD, MISREAD, PRINTED,              # a.jpg: refused
          PRINTED, PRINTED, PRINTED,                           # b.jpg: kept by two reads
          CORN_FLAKES, CORN_FLAKES, None, CORN_FLAKES)         # c.jpg: kept by the OCR text
    rows, unreadable, _ms = barcode_reads.measure(barcode_reads.photos([str(tmp_path)]),
                                                  backs={"c.jpg": CORN_FLAKES_OCR})
    assert unreadable == 0
    assert [(r["old"], r["new"], r["by_ocr"]) for r in rows] == [
        ([MISREAD], [], []), ([PRINTED], [PRINTED], []), ([CORN_FLAKES], [CORN_FLAKES], [CORN_FLAKES])]
    lines = []
    pct = barcode_reads.report(rows, 0, [], {"a.jpg": {(PRINTED, "camera")}}, out=lines.append)
    assert round(pct, 1) == 33.3
    assert any("a.jpg" in x and f"refused {MISREAD}" in x and f"{PRINTED} (camera)" in x for x in lines)
    assert any("kept by the OCR text (cloud_vision)" in x and "c.jpg" in x for x in lines)
    assert lines[-1].endswith("ABOVE - stop and report")


def test_tesseract_reads_a_back_photo_only_where_its_text_decides(monkeypatch, tmp_path):
    (tmp_path / "back.jpg").write_bytes(barcode_photo(CORN_FLAKES))
    asked = []

    def ocr(data):
        asked.append(1)
        return CORN_FLAKES_OCR
    reads(monkeypatch, CORN_FLAKES, CORN_FLAKES, None, CORN_FLAKES)
    rows, _u, _ms = barcode_reads.measure(barcode_reads.photos([str(tmp_path)]), backs={"back.jpg": None}, ocr=ocr)
    assert rows[0]["new"] == [CORN_FLAKES] and rows[0]["ocr_from"] == "tesseract" and asked == [1]
    reads(monkeypatch, CORN_FLAKES, CORN_FLAKES, CORN_FLAKES)            # two reads agree: no Tesseract
    barcode_reads.measure(barcode_reads.photos([str(tmp_path)]), backs={"back.jpg": None}, ocr=ocr)
    assert asked == [1]


def test_a_run_with_no_accepted_read_is_not_a_pass():
    lines = []
    assert barcode_reads.report([], 0, [], {}, out=lines.append) is None
    assert "TODO" in lines[-1]


def small_sharp_photo(code, px_per_module):
    """A real barcode (no stand-in), each bar module px_per_module wide, on a 1600 x 1200 photo."""
    from PIL import Image
    img = zxingcpp.create_barcode(code, zxingcpp.BarcodeFormat.EAN13).to_image(scale=8)
    h, w = img.shape[:2]
    bars = Image.frombytes("L", (w, h), bytes(memoryview(img)))
    bars = bars.resize((round(w * px_per_module / 8), round(h * px_per_module / 8)), Image.LANCZOS)
    photo = Image.new("L", (1600, 1200), 200)
    photo.paste(bars, (400, 500))
    buf = io.BytesIO()
    photo.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


def test_a_small_sharp_barcode_the_half_size_read_refused_is_accepted():
    # Bars 2.5 px wide are 1.25 px at half size, too thin to read; at three-quarter
    # size they are 1.9 px and the two reads agree. A real zxing-cpp read.
    data = small_sharp_photo(PRINTED, 2.5)
    assert barcode.read_from_photo(data, two_reads=False) == ([PRINTED], [])
    assert barcode.read_from_photo(data) == ([PRINTED], [])

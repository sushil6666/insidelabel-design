"""
D-141 (accepted 2026-09-30, first part only): a barcode read from a photo counts
only when two reads agree: the photo as before (up to 2400 px) and once more at half
size. No size threshold yet (Sushil's condition 1).

The case, from Sushil's phone check of phase 1 (2026-09-30): a small, blurry barcode
photo made zxing-cpp read 0961676012608 where the pack prints 8901058018608, and
barcode.check() accepted it (six digits wrong, check digit still right). zxing-cpp is
stood in for here: the first read of a photo gives the misread, a second read (the
rescale D-141 proposes) gives the pack's code or nothing.

The two refusals were strict xfails until D-141 was built. Sushil's condition 2:
before it ships, tools/barcode_reads.py measures the old and the new rule over the
photos the server holds; more than 5% of accepted reads refused means stop.
"""
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


def test_both_numbers_pass_the_gs1_check_which_is_why_a_second_read_is_needed():
    assert barcode.check(MISREAD) == (MISREAD, None) and barcode.check(PRINTED) == (PRINTED, None)
    assert sum(a != b for a, b in zip(MISREAD, PRINTED)) == 6


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


def test_the_refusal_says_why_and_offers_the_camera_scanner(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    assert check_barcode()["message"] == barcode.MESSAGES["barcode_unsure"]
    assert "camera scanner" in barcode.MESSAGES["barcode_unsure"]


def test_a_barcode_on_a_back_photo_follows_the_same_rule(monkeypatch):
    # D-141 point 3: "Barcode ... found on it too" only when both reads agree;
    # the back photo itself is still fine.
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


def test_the_measuring_tool_counts_what_the_new_rule_would_refuse(monkeypatch, tmp_path):
    for name in ("a.jpg", "b.jpg"):
        (tmp_path / name).write_bytes(barcode_photo(PRINTED))
    # a.jpg: one read, then the second read of the new rule; b.jpg the same.
    reads(monkeypatch, MISREAD, MISREAD, PRINTED, MISREAD, MISREAD, MISREAD)
    rows, unreadable, _ms = barcode_reads.measure(barcode_reads.photos([str(tmp_path)]))
    assert unreadable == 0
    assert [(r["old"], r["new"]) for r in rows] == [([MISREAD], []), ([MISREAD], [MISREAD])]
    lines = []
    assert barcode_reads.report(rows, 0, [], {"a.jpg": {(PRINTED, "camera")}}, out=lines.append) == 50.0
    assert any("a.jpg" in x and f"refused {MISREAD}" in x and f"{PRINTED} (camera)" in x for x in lines)
    assert lines[-1].endswith("ABOVE - stop and report")


def test_a_run_with_no_accepted_read_is_not_a_pass():
    lines = []
    assert barcode_reads.report([], 0, [], {}, out=lines.append) is None
    assert "TODO" in lines[-1]

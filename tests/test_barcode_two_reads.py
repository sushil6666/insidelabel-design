"""
D-141 (RECOMMENDED): a barcode read from a photo counts only when two reads agree
(the photo as now, and one rescale) or the barcode is big enough in the photo.

The case, from Sushil's phone check of phase 1 (2026-09-30): a small, blurry barcode
photo made zxing-cpp read 0961676012608 where the pack prints 8901058018608, and
barcode.check() accepted it (six digits wrong, check digit still right). zxing-cpp is
stood in for here: the first read of a photo gives the misread, a second read (the
rescale D-141 proposes) gives the pack's code or nothing.

Until D-141 is accepted and built, the refusals are expected failures (strict xfail):
the suite shows the gap without failing, and a build that closes it turns them into
plain passes (strict: an unexpected pass fails, so the marker must then be removed).
"""
import pytest
import zxingcpp
from fastapi.testclient import TestClient
from test_check_photo import barcode_photo

from insidelabel import barcode
from insidelabel.api import main

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


def check_barcode():
    return c.post("/check-photo", data={"role": "barcode"},
                  files={"photo": ("barcode.jpg", barcode_photo(PRINTED), "image/jpeg")}).json()


def test_both_numbers_pass_the_gs1_check_which_is_why_a_second_read_is_needed():
    assert barcode.check(MISREAD) == (MISREAD, None) and barcode.check(PRINTED) == (PRINTED, None)
    assert sum(a != b for a, b in zip(MISREAD, PRINTED)) == 6


def test_two_reads_that_agree_are_accepted(monkeypatch):
    reads(monkeypatch, PRINTED, PRINTED)
    j = check_barcode()
    assert j["ok"] and j["barcode"] == PRINTED


@pytest.mark.xfail(strict=True, reason="D-141 RECOMMENDED, not built: today one read decides")
def test_sushils_case_two_reads_that_disagree_are_refused(monkeypatch):
    reads(monkeypatch, MISREAD, PRINTED)
    j = check_barcode()
    assert not j["ok"] and j["barcode"] is None and j["problem"] == "barcode_unsure"


@pytest.mark.xfail(strict=True, reason="D-141 RECOMMENDED, not built: today one read decides")
def test_a_second_read_that_finds_nothing_is_refused(monkeypatch):
    reads(monkeypatch, MISREAD, None)
    j = check_barcode()
    assert not j["ok"] and j["barcode"] is None and j["problem"] == "barcode_unsure"

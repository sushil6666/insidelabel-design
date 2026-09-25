"""
Problems reported from the app, frozen as tests (D-092).

Each file in tests/regression/problems/ was written by
`tools/repro.py show <id> --save NAME` from a real report: the stored model
answer, OCR text (migration 007) and request options, replayed through /scan
with a 1x1 PNG. `expected`
is what the screen should show; once a fix lands it must keep showing it.
"""
import glob
import json
import os

import pytest

from insidelabel import repro

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regression", "problems")
CASES = [(os.path.basename(p), i, c)
         for p in sorted(glob.glob(os.path.join(HERE, "*.json")))
         for i, c in enumerate(json.load(open(p, encoding="utf-8"))["cases"])]


@pytest.mark.skipif(not CASES, reason="no saved problem reports yet")
@pytest.mark.parametrize("name,i,case", CASES or [("none", 0, {})])
def test_reported_problem_stays_fixed(name, i, case):
    req = case["request"]
    files = {r: (f"{r}.png", repro.PNG, "image/png") for r in (req.get("images") or ["back"])}
    got = repro.post_scan(repro.form_for(req, case["model_raw"]), files, case.get("ocr"))
    assert got["status"] == case["expected_status"], name
    assert repro.summary(got["screen"]) == case["expected"], name

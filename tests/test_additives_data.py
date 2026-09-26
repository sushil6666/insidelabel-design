"""The additive table's legal fields (D-046, D-111).

Every row says whether FSSAI permits the additive, on what basis in Appendix A, and
when that was checked against the document. D-111's badges ("Permitted in India",
"Not permitted in India") are built from these fields, so a row without them would
show a badge nobody checked. 31 rows went two releases without them; this keeps it
from happening again.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "data", "additives.json"), encoding="utf-8") as fh:
    ROWS = [r for r in json.load(fh)["additives"] if r.get("class") != "note"]

STATUSES = {"permitted", "permitted_with_limits", "not_permitted"}


def test_every_additive_row_has_its_fssai_basis_and_check_date():
    missing = [r["ins"] for r in ROWS
               if r.get("fssai_status") not in STATUSES or not r.get("fssai_basis") or not r.get("verified_on")]
    assert not missing, f"rows without fssai_status / fssai_basis / verified_on: {missing}"


def test_status_matches_its_basis():
    """GMP-table rows are "permitted"; numeric-limit rows are "permitted_with_limits";
    a number only in the INS reference list is "not_permitted" (CLAUDE.md, D-046)."""
    for r in ROWS:
        basis, status = r["fssai_basis"], r["fssai_status"]
        if status == "not_permitted":
            assert "no Appendix A provision" in basis, r["ins"]
        elif basis.startswith("GMP"):
            assert status == "permitted", r["ins"]
        else:
            assert "numeric limits" in basis and status == "permitted_with_limits", r["ins"]


def test_not_permitted_rows_are_high_concern():
    """additives.json _meta.concern_scale: "high" = not permitted in India, or a strong signal."""
    for r in ROWS:
        if r["fssai_status"] == "not_permitted":
            assert r["concern"] == "high", r["ins"]

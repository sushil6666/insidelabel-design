"""
tools/health_report.py: one JSON snapshot for the health report page (2026-09-28),
and the guard that keeps the suite out of a real database.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import health_report  # noqa: E402


def test_the_suite_never_sees_insidelabel_db():
    """conftest.py drops it: with it set, api/main.py stored every test scan in that database."""
    assert "INSIDELABEL_DB" not in os.environ


def test_snapshot_without_tests_or_database(tmp_path):
    out = tmp_path / "health.json"
    health_report.main(["--out", str(out), "--no-tests"])
    d = json.loads(out.read_text())
    assert d["tests"] is None and d["database"] is None
    statuses = {g["status"] for g in d["gates"]}
    assert statuses <= {"PASS", "FAIL", "TODO"}
    # No database means the catalogue gate is TODO, never PASS (CLAUDE.md).
    assert [g["status"] for g in d["gates"] if g["section"] == "Catalogue"] == ["TODO"]
    assert d["data"]["additives"] == d["data"]["additives_with_basis"]

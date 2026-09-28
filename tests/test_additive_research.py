"""
D-125: the "Worth a look" rows and data/additive_research.json.

A research line is shown only when its sources were read first-hand and Sushil
reviewed it (D-046); until then the row's own reason is shown. Labels invented.
"""
import json
import os

from test_screen import scan
from test_wording import assert_clean

from insidelabel.core import engine
from insidelabel.lenses import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "data", "additive_research.json"), encoding="utf-8") as fh:
    ROWS = json.load(fh)["rows"]

COLOURED = ["Wheat flour", "Sugar", "Colours (160 a(ii), 129)", "Salt"]


def test_every_research_row_has_its_sources_and_a_reviewer():
    for ins, r in ROWS.items():
        a = engine._ADDITIVE_BY_INS.get(ins)
        assert a and a["concern"] in ("moderate", "high"), ins          # only worth-knowing rows
        assert r["summary"] and all(isinstance(t, str) and t for t in r["summary"]), ins
        assert r["sources"], ins
        for s in r["sources"]:
            assert s["title"] and s["url"].startswith("https://") and len(s["read_on"]) == 10, ins
        assert r.get("reviewed_by"), ins
        assert_clean(r["summary"], ins)


def test_a_worth_knowing_additive_gets_a_closed_row():
    s = scan(COLOURED, profiles=[]).json()["screen"]
    [a] = s["alerts"]
    assert a["title"] == "Worth a look: Allura Red AC (colour 129)"
    assert a["label_line"] == "Colours (160 a(ii), 129)"
    if "129" not in ROWS:
        # Not researched yet: the row's own reason, and it says "why", not "research".
        assert a["more"] == "Tap to see why" and not a["checked"] and a["sources"] == []
        assert a["body"] == [engine._ADDITIVE_BY_INS["129"]["why"]]


def test_a_researched_row_shows_the_research_and_its_sources(monkeypatch):
    monkeypatch.setitem(screen.RESEARCH, "129", {
        "summary": ["First plain sentence.", "Second plain sentence."],
        "sources": [{"title": "A study", "url": "https://example.org/a", "read_on": "2026-09-28"}],
        "reviewed_by": "sushil"})
    [a] = scan(COLOURED, profiles=[]).json()["screen"]["alerts"]
    assert a["more"] == "Tap to see what research found" and a["checked"]
    assert a["body"] == ["First plain sentence.", "Second plain sentence."]
    assert a["sources"] == [{"title": "A study", "url": "https://example.org/a"}]


def test_no_row_for_ordinary_additives():
    assert scan(["Wheat flour", "Raising agent (500 (ii))", "Salt"], profiles=[]).json()["screen"]["alerts"] == []

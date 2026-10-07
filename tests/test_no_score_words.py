"""
D-064, D-165, D-173 follow-up (Sushil, 2026-10-07: "find all scores and remove"): there is no
score or grade, so no text a user can see says either word. A tester read "Sugar, salt and fat
quantities on the nutrition panel are not part of the score." under "What this check covers".

Shown text: every /scan screen block (a result, a partial read, refusals, D-172's blocked
read), the disclosures and the caveat details, the screen's word tables (problem labels,
retake lines, headlines), the data tables' shown fields, and the app's own strings. The one
place the word belongs is /how's "No score" section (D-165), which says there is none.
"""
import base64
import json
import os
import re

from fastapi.testclient import TestClient

from insidelabel.api import main
from insidelabel.extraction.providers import gemini
from insidelabel.lenses import screen
from insidelabel.reliability import gates
from test_screen import MASKA_CHASKA, vision
from test_web import JS, js_strings
from test_wording import CONSUMER_FIELDS, ROOT, strings

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
WORD = re.compile(r"\b(scores?|scored|scoring|grades?|graded)\b", re.I)
# Field names that hold notes for us, not copy (a table's purpose, a rule's reasoning).
NOT_SHOWN = frozenset({"_meta", "purpose", "rule", "why", "notes", "note_for_reviewers"})


def assert_no_score(texts, where):
    bad = [t for t in texts if isinstance(t, str) and WORD.search(t)]
    assert not bad, f"{where}: says score or grade\n" + "\n".join(f"  {t!r}" for t in bad)


def _scan(replay, **data):
    return c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
                  data={"replay": replay, **data}).json()


def test_the_lint_catches_the_word():
    assert WORD.search("not part of the score.") and WORD.search("Grade A")
    assert not WORD.search("underscore") and not WORD.search("upgraded")


def test_scan_screens_disclosures_and_caveats():
    answers = {
        "result": vision(MASKA_CHASKA),
        "partial": vision(MASKA_CHASKA, ingredients_status="partial"),
        "refused": vision([], ingredients_status="unreadable"),
        "blocked": gemini.blocked_marker("recitation"),                  # D-172
    }
    for name, replay in answers.items():
        for barcode in ({}, {"barcode": "8901063367456"}):
            j = _scan(replay, **barcode)
            shown = {k: j.get(k) for k in ("screen", "disclosures", "allergens")}
            caveats = [cv.get("detail") for cv in (j.get("reliability") or {}).get("caveats") or []]
            assert_no_score(list(strings(shown)) + caveats, f"/scan {name}")


def test_the_disclosure_says_what_the_check_covers():
    assert gates.ALWAYS_DISCLOSE[0] == ("The headline and findings come from the ingredient list. When we can "
                                        "read the nutrition table, its numbers are shown beside ICMR-NIN's "
                                        "guide, as information.")
    assert_no_score(gates.ALWAYS_DISCLOSE, "gates.ALWAYS_DISCLOSE")


def test_the_screens_word_tables():
    texts = []
    for name, value in vars(screen).items():
        if name.isupper():
            texts += list(strings(value, skip_keys=NOT_SHOWN))
    assert_no_score(texts, "lenses/screen.py")


def test_the_data_tables_shown_fields():
    for fname, (section, fields) in CONSUMER_FIELDS.items():
        with open(os.path.join(ROOT, "data", fname), encoding="utf-8") as f:
            rows = json.load(f)[section]
        assert_no_score([r.get(k) for r in rows for k in fields], fname)


def test_the_apps_own_strings():
    for name, src in JS.items():
        assert_no_score(js_strings(src), f"web/{name}")

"""
D-140, the last part of phase 3: the `baby` band ("Under 2 years"), `toddler` now
"2 to 3 years", and the one-time question for a phone's older toddler profiles.

What is pinned here:
- data/baby_lines.json: every line quotes a primary source read first-hand (D-046),
  with its page, basis and verified_on, and passes the wording lint (D-042).
- A baby profile gets a line only when its trigger is on this pack, and only on an
  ordinary food (or the one supplement line). An infant food, a special medical food
  or a pack that isn't food gets none: no feeding advice on an infant result (D-140).
- Nothing moves for anyone else: the lines sit in the baby's own child_facts; no
  score, band, headline or allergen line changes (D-004).
- Profiles stay ref, age and avoid (D-074); `baby` is a value, not a field.
- The question is the only new prompt and never comes on a scan that had D-146's
  digit check; the app asks one profile, once, and keeps the answer on the phone.
"""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from test_nutrition import GOLD, printed
from test_nutrition import scan as table_scan
from test_pack_kind import reading, run, st
from test_screen import scan
from test_wording import assert_clean

from insidelabel.api import main
from insidelabel.core import engine
from insidelabel.lenses import compare as kids
from insidelabel.lenses import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
TABLE = json.load(open(os.path.join(ROOT, "data", "baby_lines.json"), encoding="utf-8"))
BABY = [{"ref": "me", "age": "adult", "avoid": ["milk"]}, {"ref": "p1", "age": "baby", "avoid": []}]
TODDLER = [{"ref": "me", "age": "adult", "avoid": []}, {"ref": "p1", "age": "toddler", "avoid": []}]
# With an avoid list the baby always has a line, so "no baby line" is a real check.
BABY_AVOIDS = [BABY[0], {"ref": "p1", "age": "baby", "avoid": ["peanut"]}]
SWEET = ["Wheat flour", "Sugar", "Honey", "Iodised salt", "Sweetener (INS 955)", "Cocoa"]


def person(j, ref="p1"):
    """The profile's line, or None when it has none (no avoid list and nothing to say)."""
    return next((p for p in j["screen"]["people"] if p["ref"] == ref), None)


def baby_refs(p):
    return [f["source"]["ref"] for f in (p or {}).get("child_facts", [])
            if f.get("source", {}).get("kind") == "baby_line"]


# ---------------------------------------------------------------- the table

def test_every_line_is_sourced_dated_and_worded_within_d042():
    srcs = TABLE["_meta"]["sources"]
    assert [r["id"] for r in TABLE["lines"]] == \
        ["added_sugar", "non_sugar_sweetener", "honey", "salt", "hfss", "supplement"]
    for r in TABLE["lines"]:
        assert r["source"] in srcs and srcs[r["source"]]["url"].startswith("https://"), r["id"]
        assert r["page"] and r["basis"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["verified_on"]), r["id"]
        assert r["trigger"] in ("added_sugar", "names", "hfss", "supplement"), r["id"]
        # The line quotes its source: the quoted words are in the recorded basis.
        quoted = re.search(r"\"(.+)\"", r["text"]).group(1)
        assert quoted in r["basis"], r["id"]
    assert_clean([r["text"] for r in TABLE["lines"]], "baby_lines.json")


def test_the_sweetener_line_follows_whos_own_definition():
    row = next(r for r in TABLE["lines"] if r["id"] == "non_sugar_sweetener")
    # WHO NSS guideline p. xi: sugar alcohols and low-calorie sugars are not NSS.
    assert not {"sorbitol", "maltitol", "xylitol", "erythritol", "isomalt"} & set(row["names"])
    assert "420" not in row["ins"] and "968" not in row["ins"]
    # Every INS number is a sweetener row in the additive table, under the same substance.
    for ins in row["ins"]:
        a = engine._ADDITIVE_BY_INS.get(ins)
        if a:
            assert set(a.get("flags", [])) & {"artificial_sweetener", "sweetener_natural"}, ins


def test_whos_5a_is_not_a_line():
    # "Foods high in sugar, salt and trans fats should not be consumed": no threshold given.
    assert not any("trans fats should not" in r["text"] for r in TABLE["lines"])


# ---------------------------------------------------------------- the bands

def test_baby_is_a_value_not_a_field():
    assert kids.AGE_BANDS == ("baby", "toddler", "kid", "young")
    assert screen.parse_profiles([{"ref": "p1", "age": "baby", "avoid": ["milk"]}]) == \
        [{"ref": "p1", "age": "baby", "avoid": ["milk"]}]
    with pytest.raises(screen.ProfileError):
        screen.parse_profiles([{"ref": "p1", "age": "baby", "avoid": [], "under2_asked": True}])


def test_the_baby_band_keeps_the_toddler_lenss_stricter_tiers():
    p = kids.extract_facts(kids.Product("x", "x", ["Rice", "Water", "Sugar"]), "baby")
    assert next(f for f in p.facts if f.key.startswith("sugar_pos:")).tier == "strong"
    p = kids.extract_facts(kids.Product("x", "x", ["Water", "Caffeine"]), "baby")
    assert next(f for f in p.facts if f.key == "caffeine").tier == "strong"


# ---------------------------------------------------------------- the lines on a food

def test_each_trigger_on_the_pack_gives_its_line_and_nothing_else_moves():
    j = scan(SWEET, profiles=BABY).json()
    p = person(j)
    assert baby_refs(p) == ["added_sugar", "non_sugar_sweetener", "honey", "salt"]
    for f in p["child_facts"]:
        if f.get("source", {}).get("kind") == "baby_line":
            assert f["sources"][0]["url"].startswith("https://") and f["sources"][0]["cite"]
    assert p["status"] == "worth_knowing" and "{name}" in p["line"]
    # Nothing else changes: the same scan with a toddler instead is the same but for p1's lines.
    t = scan(SWEET, profiles=[BABY[0], {"ref": "p1", "age": "toddler", "avoid": []}]).json()
    for k in ("headline", "band", "summary", "tiles", "worth_knowing"):
        assert j["screen"][k] == t["screen"][k], k
    assert j["verdict"] == t["verdict"] and j["allergens"] == t["allergens"]
    assert person(j, "me") == person(t, "me")
    assert not baby_refs(person(t))


def test_a_plain_list_gives_no_line_and_polyols_are_not_whos_sweeteners():
    p = person(scan(["Rice", "Sorbitol", "Erythritol", "Salt substitute"], profiles=BABY).json())
    assert baby_refs(p) == []
    assert p["status"] == "nothing_flagged"


def test_only_a_baby_gets_the_lines():
    j = scan(SWEET, profiles=[{"ref": "me", "age": "adult", "avoid": []},
                              {"ref": "p2", "age": "kid", "avoid": []}]).json()
    for p in j["screen"]["people"]:
        assert not baby_refs(p)


def test_hfss_only_where_the_checked_table_is_over_table_15_1():
    g = GOLD["maliban-wafer-cheese"]                                 # added sugars 30.2 g per 100 g
    j = table_scan(g["ingredients"], g["nutrition"], printed(g["nutrition"]), g["product"].get("net_quantity"),
                   profiles=BABY)
    assert "hfss" in baby_refs(person(j))
    # No second reading: the numbers aren't shown, so the line isn't either.
    j = table_scan(g["ingredients"], g["nutrition"], None, g["product"].get("net_quantity"), profiles=BABY)
    assert "hfss" not in baby_refs(person(j))


# ---------------------------------------------------------------- other kinds

INFANT = [st("IMPORTANT NOTICE", "front"), st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"),
          st("Infant Formula", "front")]


def test_an_infant_food_gives_a_baby_no_line_and_no_question():
    j = run(reading(["Skimmed milk", "Sugar", "Honey", "Salt"], INFANT),
            profiles=BABY_AVOIDS + [TODDLER[1] | {"ref": "p2"}])
    assert j["screen"]["kind"]["code"] == "infant"
    assert person(j) is not None and not baby_refs(person(j))
    assert "band_question" not in j["screen"]


def test_a_supplement_gives_a_baby_the_2_1_line_only():
    says = [st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE")]
    j = run(reading(["Calcium carbonate", "Sucralose (INS 955)", "Sugar"], says), profiles=BABY)
    assert j["screen"]["kind"]["code"] == "supplement"
    assert baby_refs(person(j)) == ["supplement"]


def test_a_pack_that_isnt_food_gives_no_line():
    v = reading(["Amla", "Sugar", "Honey"], [st("Ayurvedic Proprietary Medicine")],
                licences=[{"text": "Drug Lic. No. 123/AYU", "face": "back"}])
    j = run(v, profiles=BABY_AVOIDS)
    assert j["screen"]["kind"]["code"] == "not_food"
    assert person(j) is not None and not baby_refs(person(j))
    assert screen.baby_lines("not_food", ["Sugar", "Honey"], True) == []
    assert screen.baby_lines("special_medical", ["Sugar", "Honey"], True) == []


# ---------------------------------------------------------------- the question

def test_a_toddler_profile_is_asked_once_and_the_words_are_the_servers():
    q = scan(SWEET, profiles=TODDLER).json()["screen"]["band_question"]
    assert q["refs"] == ["p1"]
    assert (q["text"], q["yes"], q["no"]) == ("Is {name} under 2?", "Yes, under 2", "No, 2 or older")
    assert_clean([v for v in q.values() if isinstance(v, str)], "band question")
    # No toddler on the phone: no question.
    assert "band_question" not in scan(SWEET, profiles=BABY).json()["screen"]


def test_never_on_a_scan_that_had_the_d146_digit_check():
    r = TestClient(main.app).post("/scan", files={"back": ("b.png", b"\x89PNG back", "image/png")}, data={
        "replay": json.dumps(reading(SWEET)), "profiles": json.dumps(TODDLER),
        "barcode": "8901499008343", "barcode_source": "camera", "barcode_answer": "confirmed"})
    assert r.status_code == 200, r.text
    assert "band_question" not in r.json()["screen"]
    assert screen._band_question(TODDLER, "rescanned") is None
    assert screen._band_question(TODDLER, None)["refs"] == ["p1"]


def test_never_on_a_retake():
    v = reading(SWEET)
    v.update(back_status="unreadable", ingredients_status="unreadable", ingredients=[], ingredient_lines=[],
             ingredient_count=0)
    r = TestClient(main.app).post("/scan", files={"back": ("b.png", b"\x89PNG back", "image/png")},
                                  data={"replay": json.dumps(v), "profiles": json.dumps(TODDLER)})
    assert r.json()["screen"]["state"] == "retake"
    assert "band_question" not in r.json()["screen"]


# ---------------------------------------------------------------- the app

def _web(name):
    return open(os.path.join(WEB, name), encoding="utf-8").read()


def test_the_app_has_the_bands_asks_one_profile_and_keeps_the_answer_on_the_phone():
    lib, app = _web("lib.js"), _web("app.js")
    assert '{ id: "baby", label: "Baby", sub: "Under 2 years" }' in lib
    assert '{ id: "toddler", label: "Toddler", sub: "2 to 3 years" }' in lib
    # The flag stays on the phone: the server gets ref, age and avoid only (D-074).
    assert "profiles().map(p => ({ ref: p.ref, age: p.age, avoid: p.avoid }))" in lib
    assert "under2_asked" in lib and 'p.age === "toddler" && !p.under2_asked' in lib
    # A profile saved from the editor chose from the new bands: never asked.
    assert "p.under2_asked = true;" in app
    # Every word is the server's (D-091): the card fills q.text, q.why, q.yes, q.no.
    body = app[app.index("function bandQuestion"):]
    body = body[:body.index("\n}\n")]
    assert all(k in body for k in ("q.text", "q.why", "q.yes", "q.no", "q.done_yes", "q.done_no"))
    assert not re.search(r'el\("[a-z]+", \{[^}]*\}, "[A-Z]', body)
    assert 's.band_question && s.state === "result"' in app

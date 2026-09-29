"""
D-132: "Ingredients worth knowing" and data/ingredient_notes.json.

Every sentence comes from a primary source read first-hand (D-046) and passes
the wording lint (D-042, D-071). A row is shown only once a person reviewed it
(reviewed_by), as with the D-125 research rows, so the tests that look at the
screen mark the rows reviewed first. Information only: nothing here may move a
score, a band, a headline or an allergen line. Labels are the gold set and
invented ones.
"""
import copy
import glob
import json
import os

import pytest
from test_screen import scan
from test_wording import assert_clean, strings

from insidelabel.core import engine
from insidelabel.lenses import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "data", "ingredient_notes.json"), encoding="utf-8") as fh:
    TABLE = json.load(fh)
ROWS = TABLE["rows"]
with open(os.path.join(ROOT, "data", "normalization.json"), encoding="utf-8") as fh:
    SUGARS = set(json.load(fh)["sugar_aliases"]["added_sugar"])
with open(os.path.join(ROOT, "data", "allergens.json"), encoding="utf-8") as fh:
    ALLERGENS = json.load(fh)["allergens"]

RULES = {"tile_if_top3", "tile", "details", "unnamed", "sugar_details"}
KINDS = {"refined_flour", "milled_wheat", "fat", "oil_unnamed", "fat_unnamed", "sugar", "sweetener", "salt", "caffeine"}
CHILD = [{"ref": "p1", "age": "kid", "avoid": []}]


def _names(row):
    return set(row.get("names", [])) | {n for c in row.get("conditional", []) for n in c.get("names", [])}


@pytest.fixture
def reviewed(monkeypatch):
    """Every row as if reviewed, so the screen shows it."""
    rows = {k: {**copy.deepcopy(r), "reviewed_by": "test"} for k, r in screen.NOTES.items()}
    monkeypatch.setattr(screen, "NOTES", rows)


# ---------------------------------------------------------------- the table

def test_every_row_has_its_sources_and_passes_the_wording_lint():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids))
    for r in ROWS:
        assert r["title"] and r["kind"] in KINDS and r["position_rule"] in RULES, r["id"]
        assert 1 <= len(r["summary"]) <= 3 and all(isinstance(t, str) and t for t in r["summary"]), r["id"]
        assert r["sources"], r["id"]
        for s in r["sources"]:
            assert s["title"] and s["url"].startswith("https://") and len(s["read_on"]) == 10, r["id"]
            assert "page" in s, r["id"]
        assert isinstance(r["children_only"], bool) and "reviewed_by" in r, r["id"]
        assert_clean(r["summary"] + [r["title"]], r["id"])
        # Only the sugar row, which adds to the sugar answer, matches nothing by itself.
        assert _names(r) or r["position_rule"] == "sugar_details", r["id"]


def test_the_table_speaks_only_through_its_sources():
    # D-046: no additive rules, no "may cause": a row quotes ICMR-NIN, WHO or FSSAI.
    publishers = ("ICMR-NIN", "WHO", "FSSAI", "FSS (")
    for r in ROWS:
        assert all(s["title"].startswith(publishers) for s in r["sources"]), r["id"]


def test_names_never_count_as_sugar_and_allergen_overlaps_are_known():
    for r in ROWS:
        assert not _names(r) & SUGARS, r["id"]          # sugar is counted once, by the sugar answer
    overlap = {(r["id"], a["code"]) for r in ROWS for a in ALLERGENS if _names(r) & set(a["aliases"])}
    # Maida and sooji are wheat, ghee and butter are milk: the allergen check still
    # finds them (below); a note never stands in for it.
    assert overlap == {("maida", "gluten"), ("sooji", "gluten"), ("ghee_butter", "milk")}


def test_khandsari_bura_and_misri_are_added_sugar_coconut_sugar_is_not():
    # FSSAI FPS&FA 2011 2.8.1 and 2.8.2: sucrose products, so added sugar (L&D 2020).
    assert {"khandsari", "khandsari sugar", "bura", "bura sugar", "misri", "mishri"} <= SUGARS
    assert "coconut sugar" not in SUGARS                  # no FSSAI standard defines it
    v = engine.analyze("Bura sugar, Misri, Milk solids")
    assert v["hidden_sugar_names"] == ["bura sugar", "misri"]


# ---------------------------------------------------------------- matching

@pytest.mark.parametrize("entries, expected", [
    (["Refined wheat flour (Maida)", "Sugar"], {"maida": [1]}),
    (["Wheat flour (refined)"], {"maida": [1]}),
    (["Modified starch (1442)", "Maize starch", "Corn flour"], {"refined_flour_starch": [2, 3]}),
    (["Refined wheat flour (Maida)", "Maize starch"], {"maida": [1], "refined_flour_starch": [2]}),
    (["Sooji", "Rava"], {"sooji": [1, 2]}),
    (["Edible vegetable oil (Palmolein, Palm)"], {"palm_oil": [1]}),
    (["Palm kernel oil"], {}),
    (["Hydrogenated vegetable fat", "Bakery shortening", "Vanaspati"], {"hydrogenated_fat": [1, 2, 3]}),
    (["Coconut oil", "Desiccated coconut"], {"coconut_oil": [1]}),
    (["Cocoa butter", "Peanut butter", "Butter", "Ghee"], {"ghee_butter": [3, 4]}),
    (["Margarine"], {"margarine": [1]}),
    (["Edible vegetable oil"], {"oil_unnamed": [1]}),
    (["Edible vegetable oil (Groundnut oil)"], {}),
    (["Vegetable fat", "Refined vegetable fat 20%"], {"fat_unnamed": [1, 2]}),
    (["Sweetener (INS 955)", "Humectant (420)", "Sweeteners (sorbitol)"], {"sweetener_children": [1, 3]}),
    (["Iodised salt", "Salt substitute"], {"salt": [1]}),
    (["Tea extract", "Decaffeinated coffee", "Caffeine"], {"caffeine": [1, 3]}),
])
def test_matching(entries, expected):
    got = {h["id"]: h["positions"] for h in engine.ingredient_notes(entries)}
    assert got == expected


def test_a_raw_string_is_split_as_the_tokenizer_splits_it():
    hits = engine.ingredient_notes("Refined wheat flour (Maida), Sugar, Spices (Chilli, Ghee)")
    assert {h["id"]: h["positions"] for h in hits} == {"maida": [1], "ghee_butter": [3]}


# ---------------------------------------------------------------- the screen

RUSK = ["Refined wheat flour (Maida)", "Sugar", "Hydrogenated vegetable fat", "Palm oil", "Salt", "Yeast"]


def test_nothing_is_shown_until_a_person_reviewed_the_row():
    for r in ROWS:
        if not r["reviewed_by"]:
            assert r["id"] not in json.dumps(scan(RUSK, profiles=CHILD).json()["screen"].get("ingredient_notes"))


def test_tiles_and_lines(reviewed):
    s = scan(RUSK, profiles=[]).json()["screen"]
    notes = s["ingredient_notes"]
    assert notes["title"] == "More about the ingredients"
    # Hydrogenated fat leads (the strongest of the list), then by place in the list.
    assert [t["id"] for t in notes["tiles"]] == ["hydrogenated_fat", "maida", "palm_oil"]
    hyd = notes["tiles"][0]
    assert hyd["heading"] == "Worth a look: Hydrogenated fat"
    assert hyd["more"] == "Listed 3rd of 6. Tap to see what the sources say"
    assert hyd["label_line"] == "Hydrogenated vegetable fat" and hyd["tone"] == "worth"
    assert hyd["body"] == screen.NOTES["hydrogenated_fat"]["summary"]
    assert all(src["url"].startswith("https://") for src in hyd["sources"])
    assert [ln["id"] for ln in notes["lines"]] == ["salt"]
    assert notes["lines"][0]["where"] == "Listed 5th of 6." and "heading" not in notes["lines"][0]


def test_maida_is_a_tile_only_in_the_first_three(reviewed):
    late = ["Wheat flour (Atta)", "Sugar", "Milk solids", "Refined wheat flour (Maida)"]
    notes = scan(late, profiles=[]).json()["screen"]["ingredient_notes"]
    assert notes["tiles"] == [] and [ln["id"] for ln in notes["lines"]] == ["maida"]


def test_a_named_oil_gets_no_line_an_unnamed_one_does(reviewed):
    named = scan(["Gram flour", "Edible vegetable oil (Groundnut oil)"], profiles=[]).json()["screen"]
    assert "ingredient_notes" not in named
    [line] = scan(["Gram flour", "Edible vegetable oil"], profiles=[]).json()["screen"]["ingredient_notes"]["lines"]
    assert line["body"][0] == "The oil isn't named on the pack."


def test_the_sweetener_line_is_for_children_only(reviewed):
    drink = ["Carbonated water", "Sweetener (INS 955)"]
    assert "ingredient_notes" not in scan(drink, profiles=[]).json()["screen"]
    [line] = scan(drink, profiles=CHILD).json()["screen"]["ingredient_notes"]["lines"]
    assert line["id"] == "sweetener_children" and line["children_only"]


def test_the_sugar_answer_gets_the_sources_lines_and_no_new_flag(reviewed):
    s = scan(["Wheat flour", "Sugar", "Salt"], profiles=[]).json()["screen"]
    sugar = s["summary"][0]
    assert sugar["more"]["title"] == "What the sources say about added sugar"
    assert sugar["more"]["body"] == screen.NOTES["sugar"]["summary"]
    assert "sugar" not in json.dumps(s["ingredient_notes"]["tiles"])
    assert "more" not in scan(["Wheat flour", "Salt"], profiles=[]).json()["screen"]["summary"][0]


def test_every_note_on_screen_passes_the_wording_lint(reviewed):
    everything = RUSK + ["Maize starch", "Sooji", "Coconut oil", "Ghee", "Margarine", "Edible vegetable oil",
                         "Vegetable fat", "Sweetener (INS 955)", "Caffeine"]
    s = scan(everything, profiles=CHILD).json()["screen"]
    shown = {i["id"] for part in ("tiles", "lines") for i in s["ingredient_notes"][part]}
    assert shown == {r["id"] for r in ROWS} - {"sugar"}
    assert_clean(list(strings(s["ingredient_notes"])) + list(strings(s["summary"])), "ingredient notes")


# ---------------------------------------------------------------- before and after

GOLD = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(ROOT, "gold", "*.json")))}
# What each gold label gains (tiles, lines), read off the label by hand. Limca has
# none of the ingredients; Patanjali's ghee sits inside "Milk products [...]".
GOLD_NOTES = {
    "britannia-treat-croissant-cocoa": (["maida", "palm_oil"], ["margarine", "salt"]),
    "limca-pet-1l": None,
    "limca-pet-2250": None,
    "maliban-wafer-cheese": (["maida", "palm_oil"], ["salt"]),
    "patanjali-doodh-biscuits": (["palm_oil"], ["ghee_butter", "salt"]),
    "ziggy-donut-cake-choco-vanilla": (["maida", "palm_oil"], ["refined_flour_starch", "salt"]),
}


def _gold_scan(g):
    return scan(g["ingredients"], profiles=[], allergen_statement=g.get("allergen_statement")).json()


@pytest.mark.parametrize("name", sorted(GOLD))
def test_gold_before_and_after(name, monkeypatch):
    g = GOLD[name]
    before = _gold_scan(g)
    rows = {k: {**copy.deepcopy(r), "reviewed_by": "test"} for k, r in screen.NOTES.items()}
    monkeypatch.setattr(screen, "NOTES", rows)
    after = _gold_scan(g)
    # Information only: the verdict, the allergens and every other screen field are unchanged.
    assert before["verdict"]["score"] is not None and before["screen"]["state"] == "result"
    assert after["verdict"] == before["verdict"] and after["allergens"] == before["allergens"]
    a, b = after["screen"], before["screen"]
    assert a["headline"] == b["headline"] and a["band"] == b["band"] and a["people"] == b["people"]
    for x, y in zip(a["summary"], b["summary"]):
        x = {k: v for k, v in x.items() if k != "more"}
        assert x == y
    assert {k for k in a if k not in b} == ({"ingredient_notes"} if GOLD_NOTES[name] else set())
    if GOLD_NOTES[name]:
        tiles, lines = GOLD_NOTES[name]
        assert [t["id"] for t in a["ingredient_notes"]["tiles"]] == tiles
        assert [ln["id"] for ln in a["ingredient_notes"]["lines"]] == lines
    # Every gold label has sugar, so every one gains the sources' lines under it.
    assert "more" in a["summary"][0] and "more" not in b["summary"][0]


def test_no_concerns_found_never_sits_over_a_tile(reviewed):
    # D-123: "Hydrogenated vegetable fat" is not a NOVA alias today, so this pack reads
    # clean; with its tile it gets the "mixed" words. Verdict untouched (information only).
    j = scan(["Whole wheat flour", "Hydrogenated vegetable fat", "Salt"], profiles=[]).json()
    assert j["verdict"]["binary"] == "clean" and j["verdict"]["score"] == 100
    s = j["screen"]
    assert s["headline"] == {"text": "A few things worth knowing.",
                             "source": {"kind": "ingredient_note", "ref": "hydrogenated_fat"}}
    assert s["band"]["code"] == "mixed" and "No concerns found" not in json.dumps(s)
    plain = scan(["Whole wheat flour", "Salt"], profiles=[]).json()["screen"]
    assert plain["headline"]["text"] == "No concerns found in the ingredients."

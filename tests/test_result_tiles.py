"""
D-134: the one-screen result. Every "Worth a look" row becomes a compact tile, and
each tile opens its own page, built from `screen.details[tile id]`.

The tiles regroup what the result already said (the D-111 badges, the D-125
research rows, the D-132 ingredient notes, the D-133 trans fat row): these tests
pin that nothing new is judged, that the older fields stay for app versions before
web-27, that the allergen lines stay first and apart (D-060), and that every word
on a tile's page passes the wording lint (D-042, D-071). Labels are the gold set
and invented ones.
"""
import copy
import os
import re

import pytest
from test_nutrition import GOLD, ZIGGY, gold_scan, printed
from test_nutrition import scan as table_scan
from test_screen import keys, scan
from test_wording import assert_clean, strings

from insidelabel.lenses import screen

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
READ = sorted(GOLD)                                  # all six read to a result

# Everything the tiles can come from, on one invented pack: an additive FSSAI doesn't
# permit (924a), one worth knowing (102), hydrogenated fat, maida first, palm oil, and
# a nutrition table with trans fat above zero (Ziggy's).
EVERYTHING = ["Refined wheat flour (Maida)", "Sugar", "Hydrogenated vegetable fat", "Palm oil",
              "Colour (INS 102)", "Flour treatment agent (INS 924a)", "Salt"]


def everything():
    t = copy.deepcopy(ZIGGY["nutrition"])
    return table_scan(EVERYTHING, t, printed(t), ZIGGY["product"]["net_quantity"])["screen"]


def test_every_kind_in_its_order():
    s = everything()
    assert [(t["kind"], t["id"]) for t in s["tiles"]] == [
        ("not_permitted", "ins-924a"),
        ("additive", "ins-102"),
        ("ingredient", "note-hydrogenated_fat"),          # D-132: the strongest of the notes leads
        ("ingredient", "note-maida"),
        ("ingredient", "note-palm_oil"),
        ("nutrition", "nut-trans_fat"),
    ]
    by = {t["id"]: t for t in s["tiles"]}
    assert by["ins-924a"] == {"id": "ins-924a", "kind": "not_permitted", "title": "Potassium bromate (flour treatment 924a)",
                              "chip": "Not permitted in India", "tone": "alert",
                              "source": {"kind": "additive", "ref": by["ins-924a"]["source"]["ref"]}}
    assert by["ins-102"]["chip"] == "Worth knowing" and by["ins-102"]["tone"] == "worth"
    assert by["note-maida"]["chip"] == "1st of 7" and by["note-palm_oil"]["chip"] == "4th of 7"
    assert by["nut-trans_fat"]["title"] == "Trans fat" and by["nut-trans_fat"]["chip"] == "0.03 g per 100 g"


def test_each_tile_has_its_page_and_nothing_else_does():
    s = everything()
    assert set(s["details"]) == {t["id"] for t in s["tiles"]}
    for t in s["tiles"]:
        assert re.fullmatch(r"[a-z]+-[a-z0-9_]+", t["id"]), t["id"]            # sits in a URL as it is
        assert set(t) == {"id", "kind", "title", "chip", "tone", "source"}
        assert t["kind"] in screen.TILE_KINDS
        d = s["details"][t["id"]]
        assert set(d) == {"title", "chip", "kind", "what_it_is", "what_research_found", "who_it_concerns",
                          "on_the_label", "where", "note", "sources"}
        assert d["title"] == t["title"] and d["chip"] == t["chip"] and d["kind"] == t["kind"]
        assert d["what_research_found"] and d["on_the_label"]
        # D-134: "who it concerns" only where a source says it; no reviewed row says it apart from its research yet.
        assert d["who_it_concerns"] is None
    assert len({t["id"] for t in s["tiles"]}) == len(s["tiles"])


def test_a_page_says_what_the_rows_already_said():
    s = everything()
    d = s["details"]
    # The additive FSSAI doesn't permit: that first, then the number, as the D-111 alert said it.
    assert d["ins-924a"]["note"] == (screen.ADDITIVE_ALERT + " " + s["additive_alert"]["detail"])
    assert d["ins-924a"]["what_it_is"] == "Potassium bromate is a flour treatment, INS 924a."
    assert d["ins-924a"]["on_the_label"] == "Flour treatment agent (INS 924a)"
    # An additive worth knowing: its reviewed research row (D-125), word for word, with its sources.
    alert = next(a for a in s["alerts"] if a["ins"] == "102")
    assert d["ins-102"]["what_research_found"] == alert["body"]
    assert [x["url"] for x in d["ins-102"]["sources"]] == [x["url"] for x in alert["sources"]]
    # An ingredient note: the reviewed sentences, the definition moved under "What it is".
    maida = next(n for n in s["ingredient_notes"]["tiles"] if n["id"] == "maida")
    assert [d["note-maida"]["what_it_is"], *d["note-maida"]["what_research_found"]] == maida["body"]
    assert d["note-maida"]["what_it_is"].startswith("Maida is refined wheat flour")
    assert d["note-maida"]["where"] == "Listed 1st of 7." and d["note-maida"]["sources"] == maida["sources"]
    hyd = next(n for n in s["ingredient_notes"]["tiles"] if n["id"] == "hydrogenated_fat")
    assert d["note-hydrogenated_fat"]["what_it_is"] is None and d["note-hydrogenated_fat"]["what_research_found"] == hyd["body"]
    # The nutrition table's trans fat row.
    trans = s["nutrition"]["tiles"][0]
    assert d["nut-trans_fat"]["what_research_found"] == trans["body"]
    assert d["nut-trans_fat"]["where"] == "0.03 g per 100 g on the nutrition table."


def test_an_unsure_number_is_a_tile_that_says_check_it():
    # D-111: "Not permitted" needs a sure read; below the allergen gate it is "Worth knowing" with a note.
    j = scan(["Wheat flour", "Flour treatment agent (INS 924a)"], profiles=None,
             confidence={"ingredients": 0.9, "front_claims": 0.0, "product_identity": 0.5}).json()["screen"]
    [t] = j["tiles"]
    assert t["kind"] == "additive" and t["chip"] == "Check the number" and t["tone"] == "worth"
    assert j["details"][t["id"]]["note"] == screen.CHECK_NUMBER


def test_a_plain_pack_has_no_tiles():
    s = scan(["Whole wheat flour", "Groundnut oil", "Salt", "Cumin"], profiles=None).json()["screen"]
    assert s["tiles"] == [] and s["details"] == {} and s["more_title"] == "More about this pack"


def test_a_refused_scan_has_no_tiles():
    s = scan(["Wheat flour", "Colour (INS 102)"], profiles=None, back_status="unreadable").json()["screen"]
    assert s["state"] == "retake" and "tiles" not in s


@pytest.mark.parametrize("name", READ)
def test_gold_tiles_are_the_worth_a_look_rows(name):
    s = gold_scan(name)["screen"]
    from_rows = ([f"ins-{a['ins']}" for a in s["alerts"]]
                 + [f"note-{n['id']}" for n in (s.get("ingredient_notes") or {}).get("tiles", [])]
                 + [f"nut-{n['id']}" for n in (s.get("nutrition") or {}).get("tiles", [])])
    assert sorted(t["id"] for t in s["tiles"]) == sorted(from_rows)
    assert_clean(list(strings({"tiles": s["tiles"], "details": s["details"], "more": s["more_title"]})),
                 f"tiles {name}")


def test_the_gold_tiles():
    tiles = {n: [t["id"] for t in gold_scan(n)["screen"]["tiles"]] for n in READ}
    assert tiles == {
        "britannia-treat-croissant-cocoa": ["note-maida", "note-palm_oil"],
        "limca-pet-1l": ["ins-211"],
        "limca-pet-2250": ["ins-211"],
        "maliban-wafer-cheese": ["ins-129", "note-maida", "note-palm_oil"],
        "patanjali-doodh-biscuits": ["ins-223", "note-palm_oil", "nut-trans_fat"],
        "ziggy-donut-cake-choco-vanilla": ["note-maida", "note-palm_oil", "nut-trans_fat"],
    }


def test_people_first_and_older_fields_kept():
    s = everything()
    assert list(s)[:3] == ["state", "people", "headline"]                       # D-060
    for old in ("additive_alert", "alerts", "ingredient_notes", "nutrition", "summary", "glance", "additives"):
        assert old in s, old                                                    # app versions before web-27
    assert s["nutrition"]["tiles"] and s["ingredient_notes"]["tiles"]
    assert not {"score", "grade", "display_score"} & set(keys({"t": s["tiles"], "d": s["details"]}))   # D-064


def test_information_only():
    # The tiles change what is on screen, never the engine's answer (D-004).
    t = copy.deepcopy(ZIGGY["nutrition"])
    j = table_scan(EVERYTHING, t, printed(t), ZIGGY["product"]["net_quantity"])
    s = j["screen"]
    assert s["headline"]["text"] == "Has Potassium bromate, an additive with higher concern."
    assert s["band"]["code"] == "ultra-processed"
    assert_clean(list(strings({"tiles": s["tiles"], "details": s["details"]})), "tiles, invented")


def test_the_app_renders_tiles_and_their_pages_and_composes_nothing():
    src = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    assert 'if (sub === "look") return lookView(h, tileId);' in src
    assert "h.screen.details?.[tileId]" in src
    assert "#/result/${encodeURIComponent(h.id)}/look/${encodeURIComponent(t.id)}" in src
    assert "...rest.map(decodeURIComponent)" in src                            # the router passes the tile id
    # D-091: a tile's words are the server's: title and chip, never built from other fields.
    tile = re.search(r"function tileLink\(h, t\) \{(.*?)\n\}", src, re.S).group(1)
    assert "t.title" in tile and "t.chip" in tile


def test_what_it_is_points_at_one_of_the_rows_own_sentences():
    # data/ingredient_notes.json: `what_it_is` only moves a reviewed sentence, never adds one.
    from test_ingredient_notes import ROWS
    marked = {r["id"]: r["what_it_is"] for r in ROWS if "what_it_is" in r}
    assert marked == {"maida": 0}
    for r in ROWS:
        if "what_it_is" in r:
            assert isinstance(r["what_it_is"], int) and 0 <= r["what_it_is"] < len(r["summary"])

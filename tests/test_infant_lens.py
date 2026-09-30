"""
D-140 phase 3, in shadow: an infant food's own checks (lenses/infant.py over
data/infant_rules.json, read from the FSS (Foods for Infant Nutrition) Regulations
2020 compendium's page images on 2026-09-30). Invented labels; the rows are pinned
to their pages.
"""
import json
import os

from test_pack_kind import reading, st

from insidelabel.lenses import infant

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = json.load(open(os.path.join(HERE, "..", "data", "infant_rules.json"), encoding="utf-8"))

NOTICE = [st("IMPORTANT NOTICE", "back"), st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"),
          st("Infant food shall be introduced only after the age of six months and up to the age of two years"),
          st("Infant milk substitute or infant food should be used only on the advice of a health worker "
             "as to the need for its use and the proper method of its use"),
          st("Infant milk substitute or infant food is not the sole source of nourishment of an infant"),
          st("Warning/Caution-Careful and hygienic preparation of infant foods is most essential for health"),
          st("Store in a cool and dry place in an air tight container"),
          st("Warning: Boiled and cooled water shall be used to prepare this product")]
CEREAL = ["Rice flour", "Milk solids", "Sugar", "Minerals", "Vitamins"]


def cereal(statements=NOTICE, ingredients=CEREAL, **kw):
    return reading(ingredients, [st("Processed Cereal Based Complementary Food", "front")] + list(statements), **kw)


# ---------------------------------------------------------------- the data rows

def test_every_row_names_its_page_and_the_day_it_was_read():
    rows = RULES["types"] + RULES["statements"] + RULES["no_hydrogenated"]["rows"] + RULES["reviewer_checks"]
    rows += [RULES["words_not_to_use"], RULES["free_from"]]
    for r in rows:
        basis = r.get("fssai_basis") or r.get("basis")
        assert basis and "PDF p." in basis and r["verified_on"] == "2026-09-30", r


def test_the_four_hydrogenated_sentences_are_the_regulations_words():
    rows = {r["type"]: (r["text"], r["fssai_basis"]) for r in RULES["no_hydrogenated"]["rows"]}
    assert rows["infant_formula"] == ("Hydrogenated vegetable oils and fats shall not be used in infant formula.",
                                      "7(1)(c), PDF p. 7")
    assert rows["follow_up_formula"][1] == "10(1)(d), PDF p. 25" and "traditional" not in rows


# ---------------------------------------------------------------- the product type

def test_the_type_comes_from_the_front_words_not_the_mandatory_statements():
    assert infant.product_type(cereal())["id"] == "processed_cereal"
    # the health worker statement names "infant milk substitute", whatever the type
    v = reading(CEREAL, NOTICE)
    assert infant.product_type(v) is None
    assert infant.product_type(reading(["Milk solids"], NOTICE, name="Lactogen Infant Formula"))["id"] == "infant_formula"
    assert infant.product_type(reading(["Milk solids"], NOTICE, name="Follow-up Formula Stage 2"))["id"] == \
        "follow_up_formula"


# ---------------------------------------------------------------- regulation 4

def test_every_statement_found_on_a_complete_label():
    got = infant.statements(cereal(), ptype=infant.product_type(cereal()))
    assert [s["id"] for s in got if not s["found"]] == []
    assert {s["id"] for s in got} >= {"mothers_milk", "six_months", "boiled_water"}


def test_a_missing_statement_is_not_found_with_its_basis():
    v = cereal(statements=[s for s in NOTICE if "Boiled" not in s["text"]])
    (miss,) = [s for s in infant.statements(v, ptype=infant.product_type(v)) if not s["found"]]
    assert miss["id"] == "boiled_water" and miss["basis"] == "4(6), PDF p. 6"


def test_mothers_milk_must_be_on_the_front():
    v = cereal(statements=[st("MOTHER'S MILK IS BEST FOR YOUR BABY", "back")] + NOTICE[2:])
    got = {s["id"]: s["found"] for s in infant.statements(v, ptype=infant.product_type(v))}
    assert got["mothers_milk"] is False


def test_the_six_months_line_is_for_infant_food_not_infant_formula():
    v = reading(["Milk solids"], NOTICE, name="Infant Formula")
    assert "six_months" not in {s["id"] for s in infant.statements(v, ptype=infant.product_type(v))}


def test_nothing_is_said_without_both_faces_read_whole():
    assert infant.statements(cereal(front="unreadable")) is None


def test_the_ocr_text_finds_a_statement_the_model_left_out():
    v = cereal(statements=[s for s in NOTICE if "Boiled" not in s["text"]])
    got = infant.statements(v, "WARNING: BOILED AND COOLED WATER SHALL BE USED", infant.product_type(v))
    assert all(s["found"] for s in got)


# ---------------------------------------------------------------- 4(2), 5(1), hydrogenated fat

def test_words_the_label_shall_not_exhibit():
    v = cereal(statements=NOTICE + [st("The complete Energy Food for your baby", "front")])
    assert infant.words(v) == [{"word": "energy food", "printed": "The complete Energy Food for your baby"}]
    assert infant.words(cereal(), "Maternalised protein blend")[0] == {"word": "maternalised", "printed": None}
    assert infant.words(cereal()) == []


def test_preservatives_colours_and_flavours_on_the_list():
    got = infant.free_from(["Rice flour", "Preservative (INS 211)", "Added flavour (vanilla)",
                            "Flavour enhancer (INS 621)", "Colour (INS 102)"])
    assert got == [{"entry": "Preservative (INS 211)", "why": ["preservative"]},
                   {"entry": "Added flavour (vanilla)", "why": ["flavour"]},
                   {"entry": "Colour (INS 102)", "why": ["colour"]}]


def test_hydrogenated_fat_by_type():
    ings = ["Rice flour", "Hydrogenated vegetable fat", "Non-hydrogenated palm oil"]
    got = infant.hydrogenated(ings, infant.product_type(cereal()))
    assert [h["entry"] for h in got] == ["Hydrogenated vegetable fat"] and got[0]["basis"] == "9(1)(d), PDF p. 19"
    follow = infant.product_type(reading(["x"], name="Follow-up Formula"))
    assert infant.hydrogenated(ings, follow) == []                          # "partially" only
    assert len(infant.hydrogenated(["Partially hydrogenated oil"], follow)) == 1
    trad = infant.product_type(reading(["x"], [st("Traditional Food for Infants", "front")]))
    assert trad["id"] == "traditional" and infant.hydrogenated(ings, trad) == []   # no such sentence
    assert infant.hydrogenated(ings, None) == []


def test_check_gathers_everything_with_the_reviewers_own_check():
    got = infant.check(cereal(ingredients=CEREAL + ["Added flavour"]))
    assert got["type"]["id"] == "processed_cereal" and got["complete_read"]
    assert got["free_from"][0]["entry"] == "Added flavour"
    assert got["reviewer_checks"][0]["id"] == "no_pictures"

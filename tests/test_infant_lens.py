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
    rows += [RULES["words_not_to_use"], RULES["free_from"], RULES["no_milk"]]
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


# ---------------------------------------------------------------- 5(2): each type's additive list

ADDS = json.load(open(os.path.join(HERE, "..", "data", "infant_additives.json"), encoding="utf-8"))


def test_every_additive_row_is_on_its_page():
    pages = {"infant_formula": range(10, 13), "milk_cereal": range(15, 19), "processed_cereal": range(20, 25),
             "follow_up_formula": range(27, 30)}
    counts = {t: len(ADDS["types"][t]["rows"]) for t in pages}
    assert counts == {"infant_formula": 28, "milk_cereal": 70, "processed_cereal": 70, "follow_up_formula": 29}
    for t, span in pages.items():
        assert all(r["page"] in span and r["max"] for r in ADDS["types"][t]["rows"]), t
    assert [r["ins"] for r in ADDS["carriers"]["rows"]] == ["414", "551", "421", "1450", "301"]
    assert ADDS["types"]["traditional"]["same_as"] == "milk_cereal"


def test_processed_cereal_prints_the_milk_cereal_rows():
    strip = [[(r["name"], r["ins"], r["max"]) for r in ADDS["types"][t]["rows"]] for t in ("milk_cereal", "processed_cereal")]
    assert strip[0] == strip[1]


def test_the_follow_up_misprint_is_kept_as_printed():
    (row,) = [r for r in ADDS["types"]["follow_up_formula"]["rows"] if r["name"] == "Sodium hydroxide"]
    assert row["ins"] == "525" and "potassium hydroxide" in row["note"]


def test_roman_sub_numbers_and_letter_suffixes():
    assert infant._key("500ii") == infant._key("500i") == "500" and infant._key("472c") == "472c"
    _b, keys = infant.type_additives("infant_formula")
    assert {"500", "339", "472c", "307b", "304", "414", "421"} <= keys and "472e" not in keys
    _b, keys = infant.type_additives("follow_up_formula")
    assert {"307a", "307c", "322"} <= keys and "524" not in keys          # printed 525 twice (sic)


def test_additives_not_in_the_types_list():
    mc = {"id": "milk_cereal"}
    got = infant.additives(["Rice flour", "Emulsifier (INS 471)", "Acidity regulator (INS 500(ii))",
                            "Preservative (INS 211)", "Emulsifier (INS 472e)"], mc)
    assert [a["ins"] for a in got["not_found"]] == ["211", "472e"] and got["basis"].startswith("8(2)(a)")
    # infant formula's list is shorter: 1404 is only in the cereal lists
    assert infant.additives(["Thickener (INS 1404)"], {"id": "infant_formula"})["not_found"][0]["ins"] == "1404"
    assert infant.additives(["Thickener (INS 1404)"], {"id": "traditional"})["not_found"] == []   # 11(2)
    # a carrier from Schedule I(d) is on every list
    assert infant.additives(["Mannitol (INS 421)"], {"id": "processed_cereal"})["not_found"] == []


def test_nutrient_sources_and_an_unknown_type_are_left_alone():
    assert infant.additives(["Minerals (Calcium carbonate (INS 170i), Ferric pyrophosphate)"],
                            {"id": "infant_formula"})["not_found"] == []
    assert infant.additives(["Preservative (INS 211)"], None) is None
    assert infant.check(cereal(ingredients=CEREAL + ["Emulsifier (INS 472e)"]))["additives"]["not_found"] == [
        {"entry": "Emulsifier (INS 472e)", "ins": "472e"}]


# ---------------------------------------------------------------- 4(3): no milk

RICE = ["Rice flour", "Sugar", "Minerals", "Vitamins"]
NO_MILK = st("Contains no milk or milk products or milk derivatives")


def test_a_list_without_milk_needs_the_no_milk_statement():
    got = infant.no_milk(cereal(ingredients=RICE, statements=NOTICE + [NO_MILK]))
    assert got["found"] and got["basis"] == "4(3), PDF p. 6"
    got = infant.no_milk(cereal(ingredients=RICE))
    assert got["found"] is False and got["printed"] is None
    assert infant.no_milk(cereal(ingredients=RICE), "CONTAINS NO MILK OR MILK PRODUCTS")["found"]


def test_milk_on_the_list_or_a_doubt_says_nothing():
    assert infant.no_milk(cereal()) is None                                           # milk solids
    assert infant.no_milk(cereal(ingredients=RICE, allergen="May contain milk")) is None
    assert infant.no_milk(cereal(ingredients=RICE, front="unreadable")) is None
    low = cereal(ingredients=RICE)
    low["confidence"]["ingredients"] = 0.9                                            # below D-072's gate
    assert infant.no_milk(low) is None
    assert infant.check(cereal(ingredients=RICE))["no_milk"]["found"] is False


# ---------------------------------------------------------------- part 4: composition (reviewers only)

COMP = json.load(open(os.path.join(HERE, "..", "data", "infant_composition.json"), encoding="utf-8"))


def mc_reading(rows, basis="Per 100 g"):
    v = reading(["Wheat flour", "Milk solids"], [st("Milk Cereal Based Complementary Food", "front")])
    v["nutrition"] = {"status": "read", "per_100_basis": basis,
                      "rows": [{"nutrient": n, "per_100": c, "unit": u} for n, c, u in rows]}
    return v


def test_every_composition_row_names_its_page():
    counts = {t: len(v["rows"]) for t, v in COMP["types"].items()}
    assert counts == {"infant_formula": 30, "milk_cereal": 27, "processed_cereal": 18, "follow_up_formula": 25}
    for t, v in COMP["types"].items():
        for r in v["rows"]:
            assert "PDF p." in r["fssai_basis"] and r["verified_on"] == "2026-09-30" and r["unit"] in ("g", "mg", "mcg"), r
    assert "traditional" not in COMP["types"] and "folate" not in json.dumps(COMP["types"])


def test_the_18_october_2022_revisions_replace_the_compendium():
    rows = {(t, r["nutrient"]): r for t, v in COMP["types"].items() for r in v["rows"]}
    assert rows[("processed_cereal", "iron")]["per_100_g"] == [2.0, 5.65]
    assert rows[("processed_cereal", "iron")]["compendium"]["per_100_g"] == [3.0, 5.65]
    for t in ("infant_formula", "milk_cereal", "processed_cereal", "follow_up_formula"):
        assert rows[(t, "selenium")]["per_100_g"] == [5.0, 40.0] and "direction of 18.10.2022" in rows[(t, "selenium")]["fssai_basis"]
    assert rows[("follow_up_formula", "manganese")]["per_100_g"] == [5.0, 500.0]
    assert rows[("follow_up_formula", "biotin")]["per_100_g"] == [7.5, 50.0]
    assert rows[("infant_formula", "iron")]["per_100_g"] == [3.0, 7.0]               # not revised
    assert rows[("processed_cereal", "total_fat")]["per_100_g"] == [None, 7.5]        # 9(1)(f) item 3: "Max"


def test_composition_sets_printed_numbers_beside_the_range():
    v = mc_reading([("Protein", "15.5 g", None), ("Iron", "8", "mg"), ("Selenium", "0.03 mg", None)])
    got = {c["nutrient"]: c for c in infant.composition(v, "Protein 15.5 g Iron 8 mg Selenium 0.03 mg",
                                                         infant.product_type(v))}
    assert got["protein"]["where"] == "within" and got["protein"]["range"] == [15.0, None]
    assert got["iron"]["where"] == "above" and got["iron"]["basis"] == "8(1)(d) item 15, PDF p. 14"
    assert got["selenium"]["value"] == 30.0 and got["selenium"]["range_unit"] == "mcg" and got["selenium"]["optional"]


def test_what_composition_never_reads():
    v = mc_reading([("Vitamin D", "200 IU", None), ("Zinc", "3.1 mg", None), ("Calcium : Phosphorus ratio", "1.5", None)])
    assert infant.composition(v, "Vitamin D 200 IU Calcium Phosphorus ratio 1.5", infant.product_type(v)) == []
    assert infant.composition(mc_reading([("Iron", "8 mg", None)], "Per 100 ml"), "Iron 8 mg",
                              infant.product_type(v)) is None                          # not per 100 g
    assert infant.composition(mc_reading([("Iron", "8 mg", None)]), "", infant.product_type(v)) is None
    assert infant.composition(mc_reading([("Iron", "8 mg", None)]), "Iron 8 mg", None) is None
    trad = {"id": "traditional", "chapter": "infant_food"}
    assert infant.composition(mc_reading([("Iron", "8 mg", None)]), "Iron 8 mg", trad) is None

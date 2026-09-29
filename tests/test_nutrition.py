"""
D-133: the nutrition table, read by the model, judged by rules (lenses/nutrition.py)
and set beside ICMR-NIN's own thresholds (lenses/screen.py).

The gold tables are Sushil's photos transcribed by hand (gold/*.json "nutrition").
A second reading of the photo is stood in for by the table's own printed text,
the way tests stand in for Cloud Vision everywhere (cloud_vision.replaying).
Information only: nothing here may move a score, a band or an allergen line.
"""
import copy
import glob
import json
import os

import pytest
from fastapi.testclient import TestClient
from test_wording import assert_clean, strings

from insidelabel.api import main
from insidelabel.extraction.providers import cloud_vision, gemini
from insidelabel.lenses import nutrition as N
from insidelabel.lenses import screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8"))
        for f in sorted(glob.glob(os.path.join(ROOT, "gold", "*.json")))}
READABLE = ["limca-pet-2250", "maliban-wafer-cheese", "patanjali-doodh-biscuits", "ziggy-donut-cake-choco-vanilla"]
c = TestClient(main.app)
PHOTO = b"\xff\xd8\xff\xe0nutrition-back"


def printed(table, extra=""):
    """What a second reader sees: every printed cell of the table."""
    cells = [table.get("serving_size"), table.get("servings_per_pack"), table.get("per_100_basis")]
    for r in table.get("rows") or []:
        cells += [r["nutrient"], r.get("unit"), r.get("per_100"), r.get("per_serving"), r.get("rda_percent")]
    return " ".join(str(x) for x in cells if x) + " " + extra


def vision(ingredients, table=None, net=None):
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": None, "name": None, "variant": None, "net_quantity": net, "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
         "ingredients": ingredients, "allergen_statement": None, "front_claims": [],
         "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    if table is not None:
        v["nutrition"] = table
    return v


def scan(ingredients, table=None, ocr=None, net=None, profiles=None):
    """/scan with a recorded answer; `ocr` is the second reading (None: no second reading)."""
    text = None if ocr is None else "INGREDIENTS: " + ", ".join(ingredients) + ". " + ocr
    with cloud_vision.replaying({cloud_vision.digest(PHOTO): text} if text else {}):
        r = c.post("/scan", files={"back": ("b.jpg", PHOTO, "image/jpeg")},
                   data={"replay": json.dumps(vision(ingredients, table, net)),
                         **({"profiles": json.dumps(profiles)} if profiles else {})})
    assert r.status_code == 200, r.text
    return r.json()


def gold_scan(name, table=None, ocr=None):
    g = GOLD[name]
    table = g["nutrition"] if table is None else table
    return scan(g["ingredients"], table, printed(table) if ocr is None else ocr, g["product"].get("net_quantity"))


# ---------------------------------------------------------------- the data

def test_thresholds_are_icmr_nin_table_15_1():
    t = N.THRESHOLDS
    assert {k: v for k, v in t["per_100"]["solid"].items()} == \
        {"basis": "100 g", "energy_kcal": 250, "salt_mg": 625, "added_sugar_g": 3, "added_fat_g": 4.2}
    assert {k: v for k, v in t["per_100"]["liquid"].items()} == \
        {"basis": "100 ml", "energy_kcal": 70, "salt_mg": 175, "added_sugar_g": 2.0, "added_fat_g": 1.5}
    assert t["per_100"]["_source"]["page"].startswith("p. 96")
    assert t["daily"]["added_sugar_g"]["value"] == 25 and t["daily"]["salt_g"]["value"] == 5
    assert t["who_energy_share"]["saturated_fat_pct"] == 10 and t["who_energy_share"]["trans_fat_pct"] == 1
    assert t["salt_per_sodium"]["value"] == 2.5                     # WHO: 1 g salt = 400 mg sodium
    sources = [t["per_100"]["_source"], t["who_energy_share"]["_source"], t["salt_per_sodium"]["_source"],
               *t["daily"]["added_sugar_g"]["sources"], *t["daily"]["salt_g"]["sources"],
               *t["trans_fat_tile"]["sources"]]
    for s in sources:
        assert s["url"].startswith("https://") and len(s["read_on"]) == 10 and "page" in s
    assert_clean(t["trans_fat_tile"]["summary"], "trans fat tile")


def test_rda_bases_are_fssai_labelling_5_3_b():
    assert N.RDA == {"energy": 2000, "total_fat": 67, "saturated_fat": 22, "trans_fat": 2,
                     "added_sugars": 50, "sodium": 2000}


# ---------------------------------------------------------------- reading a table

@pytest.mark.parametrize("label, key", [
    ("-Added sugars", "added_sugars"), ("TOTAL SUGARS", "total_sugars"), ("of which sugars", "total_sugars"),
    ("-Saturated fat (not more than)", "saturated_fat"),
    ("TRANS FAT (OTHER THAN NATURALLY OCCURING TRANS FAT)", "trans_fat"), ("Total Fat", "total_fat"),
    ("Energy (kcal)", "energy"), ("Energy from fat", "ignore"), ("Monounsaturated fatty acids", "ignore"),
    ("Total Carbohydrates", "carbohydrate"), ("Sodium", "sodium"), ("Dietary fibre", "dietary_fibre"),
    ("Vitamin C", "ignore"), ("Salt", "salt"), ("Wibble", None),
])
def test_which_row_is_which(label, key):
    assert N.nutrient_key(label) == key


@pytest.mark.parametrize("cell, key, label, unit, want", [
    ("473.8 kcal (2.8%)", "energy", None, None, (473.8, "473.8", None)),
    ("1884 kJ / 450 kcal", "energy", None, None, (450.0, "450", None)),
    ("1884 kJ", "energy", "Energy", None, None),                     # never converted
    ("398.64", "energy", "Energy", "kcal", (398.64, "398.64", None)),
    ("22.24g", "added_sugars", None, None, (22.24, "22.24", None)),
    ("0.39 g", "sodium", "Sodium", None, (390.0, "0.39", None)),
    ("<0.1 g", "trans_fat", None, None, (0.1, "0.1", "lt")),
    ("0.09g", "trans_fat", "-Trans fat (not more than)", None, (0.09, "0.09", "max")),
    ("2,5 g", "protein", None, None, (2.5, "2,5", None)),
    ("-", "protein", None, None, None), ("", "protein", None, None, None), (None, "protein", None, None, None),
])
def test_reading_a_cell(cell, key, label, unit, want):
    got = N.read_cell(cell, key, label, unit)
    assert (None if got is None else (got["value"], got["printed"], got["bound"])) == want


@pytest.mark.parametrize("text, want", [
    ("12g", (12.0, "g", "12")), ("200 ml", (200.0, "ml", "200")), ("1 croissant (45 g)", (45.0, "g", "45")),
    ("2.25 L", (2250.0, "ml", "2.25")), ("102 g (2 packs x 51 g)", (102.0, "g", "102")), ("two", None),
])
def test_amounts(text, want):
    assert N.amount(text) == want


@pytest.mark.parametrize("name", READABLE)
def test_every_gold_table_passes_every_check(name):
    g = GOLD[name]
    p = N.check(g["nutrition"], printed(g["nutrition"]), g["product"].get("net_quantity"))
    assert p["status"] == "read" and p["dropped"] == [], p["dropped"]
    assert {k: v["value"] for k, v in p["values"].items()} == N.numbers(g["nutrition"])
    assert p["serving"] and p["servings"]


def test_a_table_cut_off_or_absent():
    assert N.check(GOLD["britannia-treat-croissant-cocoa"]["nutrition"], "text")["status"] == "unclear"
    assert N.check(GOLD["limca-pet-1l"]["nutrition"], "text")["status"] == "missing"
    assert N.check(None, "text") == {"status": "not_read"}          # an answer from before D-133


# ---------------------------------------------------------------- each check catches a misread

ZIGGY = GOLD["ziggy-donut-cake-choco-vanilla"]


def ziggy(edit=None, ocr_extra=""):
    t = copy.deepcopy(ZIGGY["nutrition"])
    if edit:
        edit(t)
    return N.check(t, printed(t, ocr_extra), ZIGGY["product"]["net_quantity"])


def _row(t, key):
    return next(r for r in t["rows"] if N.nutrient_key(r["nutrient"]) == key)


def test_a_number_the_second_reading_doesnt_have_is_dropped():
    t = copy.deepcopy(ZIGGY["nutrition"])
    p = N.check(t, printed(t).replace("20.26", "20.2 6"), ZIGGY["product"]["net_quantity"])
    assert "added_sugars" not in p["values"] and p["status"] == "partial"
    assert {"key": "added_sugars", "reason": "not in the second reading"} in p["dropped"]


def test_two_rows_swapped_are_both_dropped():
    def swap(t):
        a, f = _row(t, "added_sugars"), _row(t, "total_fat")
        a["per_100"], f["per_100"] = f["per_100"], a["per_100"]
    p = ziggy(swap)
    assert "added_sugars" not in p["values"] and "total_fat" not in p["values"]
    assert "energy" in p["values"] and p["serving"]                  # the rest stands


def test_a_misread_serving_size_is_dropped_and_the_numbers_stay():
    def serving(t):
        t["serving_size"] = "15 g"
    p = ziggy(serving)
    assert p["serving"] is None and p["status"] == "read" and len(p["values"]) == 10


def test_sugars_above_carbohydrate_drop_both():
    def sugars(t):
        _row(t, "total_sugars")["per_100"] = "60.00"
    p = ziggy(sugars)
    assert "total_sugars" not in p["values"] and "carbohydrate" not in p["values"]


def test_saturated_above_total_fat_drops_both():
    t = {"status": "read", "per_100_basis": "Per 100 g", "rda_column": None, "serving_size": None,
         "servings_per_pack": None, "rows": [
             {"nutrient": "Energy", "unit": None, "per_100": "450 kcal", "per_serving": None, "rda_percent": None},
             {"nutrient": "Total fat", "unit": None, "per_100": "5 g", "per_serving": None, "rda_percent": None},
             {"nutrient": "Saturated fat", "unit": None, "per_100": "9 g", "per_serving": None, "rda_percent": None}]}
    p = N.check(t, printed(t))
    assert set(p["values"]) == {"energy"} and p["status"] == "partial"


def test_salt_that_isnt_sodium_x_2_5_drops_both():
    t = {"status": "read", "per_100_basis": "Per 100 g", "rda_column": None, "serving_size": None,
         "servings_per_pack": None, "rows": [
             {"nutrient": "Sodium", "unit": None, "per_100": "400 mg", "per_serving": None, "rda_percent": None},
             {"nutrient": "Salt", "unit": None, "per_100": "2 g", "per_serving": None, "rda_percent": None}]}
    assert N.check(t, printed(t))["status"] == "unclear"
    t["rows"][1]["per_100"] = "1.0 g"
    assert set(N.check(t, printed(t))["values"]) == {"sodium", "salt"}


def test_servings_that_dont_make_the_net_quantity_are_dropped():
    def servings(t):
        t["servings_per_pack"] = "3"
    p = ziggy(servings)
    assert p["serving"] is None and p["servings"] is None and len(p["values"]) == 10


def test_a_printed_per_serving_amount_must_fit():
    def per_serving(t):
        _row(t, "protein")["per_serving"] = "9.5 g"                 # 5.66 x 51 / 100 is 2.89
    p = ziggy(per_serving, "9.5")
    assert "protein" not in p["values"] and p["serving"]


def test_without_a_second_reading_nothing_is_shown():
    p = N.check(ZIGGY["nutrition"], "")
    assert p["status"] == "unverified" and p["values"] == {}


def test_a_table_that_isnt_per_100_is_not_used():
    t = copy.deepcopy(ZIGGY["nutrition"])
    t["per_100_basis"] = "Per serve"
    assert N.check(t, printed(t))["status"] == "unclear"


def test_the_model_cant_invent_a_status():
    v = json.loads(json.dumps(vision(["Wheat flour"], {"status": "great", "rows": "no"})))
    fixed, corrections = gemini.harden(v, sent_front=False, sent_back=True)
    assert fixed["nutrition"]["status"] == "unreadable" and fixed["nutrition"]["rows"] == []
    assert any("nutrition.status" in x for x in corrections)


# ---------------------------------------------------------------- older answers

def test_an_answer_from_before_d133_still_parses_and_replays_the_same():
    raw = json.dumps(vision(["Wheat flour", "Sugar"]))
    assert "nutrition" not in gemini.parse_vision_json(raw)
    j = scan(["Wheat flour", "Sugar"], None, "Wheat flour Sugar")
    assert "nutrition" not in j["screen"] and j["nutrition"] is None


# ---------------------------------------------------------------- the screen

SOLID = {"status": "read", "per_100_basis": "Per 100 g", "rda_column": None, "serving_size": "30 g",
         "servings_per_pack": None, "rows": [
             {"nutrient": "Energy", "unit": None, "per_100": "480 kcal", "per_serving": None, "rda_percent": None},
             {"nutrient": "Carbohydrate", "unit": None, "per_100": "60 g", "per_serving": None, "rda_percent": None},
             {"nutrient": "Total sugars", "unit": None, "per_100": "20 g", "per_serving": None, "rda_percent": None},
             {"nutrient": "Added sugars", "unit": None, "per_100": "18 g", "per_serving": None, "rda_percent": None}]}


def test_the_two_sentences_in_the_decision():
    n = scan(["Wheat flour", "Sugar"], SOLID, printed(SOLID))["screen"]["nutrition"]
    added = next(r for r in n["rows"] if r["key"] == "added_sugars")
    assert added["text"] == "Added sugar: 18 g per 100 g. ICMR-NIN counts more than 3 g per 100 g as high."
    assert added["tone"] == "worth"
    assert n["servings"][0]["text"] == ("One serving (30 g) has 5.4 g added sugar, about a fifth of the "
                                        "25 g a day ICMR-NIN counts as high.")
    assert n["adults"] == "The daily amounts are for adults."


def test_a_drink_uses_the_per_100_ml_thresholds():
    n = gold_scan("limca-pet-2250")["screen"]["nutrition"]
    rows = {r["key"]: r for r in n["rows"]}
    assert n["basis"] == "Per 100 ml"
    assert rows["energy"]["text"] == "Energy: 44 kcal per 100 ml. ICMR-NIN counts more than 70 kcal per 100 ml as high."
    assert rows["energy"]["tone"] == "calm"
    assert rows["added_sugars"]["text"] == \
        "Added sugar: 10.7 g per 100 ml. ICMR-NIN counts more than 2 g per 100 ml as high."
    assert rows["salt"]["text"] == ("Salt: about 14 mg per 100 ml, from 5.6 mg of sodium (salt is 2.5 times the "
                                    "sodium). ICMR-NIN counts more than 175 mg of salt per 100 ml as high.")
    assert n["servings"][0]["text"] == ("One serving (200 ml) has 21.4 g added sugar, about 86% of the "
                                        "25 g a day ICMR-NIN counts as high.")
    assert n["tiles"] == []                                          # no trans fat row


def test_saturated_fat_is_set_against_its_share_of_energy():
    n = gold_scan("ziggy-donut-cake-choco-vanilla")["screen"]["nutrition"]
    sat = next(r for r in n["rows"] if r["key"] == "saturated_fat")
    # 7.45 g x 9 kcal/g (FSSAI's factor) of 398.64 kcal
    assert sat["text"] == ("Saturated fat: 7.45 g per 100 g, about 17% of the food's energy. WHO advises no "
                           "more than 10% of daily energy from saturated fat.")
    assert sat["tone"] == "worth"
    assert n["also"] == ("Also on the table, per 100 g: Protein 5.66 g, Carbohydrate 55.93 g, Total sugars "
                         "27.85 g, Total fat 16.92 g, Cholesterol 0.82 mg.")


def test_trans_fat_above_zero_gets_a_tile_zero_doesnt():
    z = gold_scan("ziggy-donut-cake-choco-vanilla")["screen"]
    [tile] = z["nutrition"]["tiles"]
    assert tile["heading"] == "Worth a look: Trans fat" and tile["kind"] == "nutrition"
    assert tile["more"].startswith("0.03 g per 100 g on the nutrition table.")
    assert tile["body"] == N.THRESHOLDS["trans_fat_tile"]["summary"]
    assert gold_scan("maliban-wafer-cheese")["screen"]["nutrition"]["tiles"] == []
    # "Not more than 0.09 g" is still trans fat declared on the table.
    p = gold_scan("patanjali-doodh-biscuits")["screen"]["nutrition"]
    assert p["tiles"][0]["more"].startswith("not more than 0.09 g per 100 g")


def test_the_headline_is_the_ingredients_one_but_never_no_concerns_over_a_tile():
    table = copy.deepcopy(ZIGGY["nutrition"])
    j = scan(["Whole wheat flour", "Salt"], table, printed(table), ZIGGY["product"]["net_quantity"])
    assert j["verdict"]["binary"] == "clean"
    assert j["screen"]["headline"] == {"text": "A few things worth knowing.",
                                       "source": {"kind": "nutrition", "ref": "trans_fat"}}
    assert gold_scan("ziggy-donut-cake-choco-vanilla")["screen"]["headline"]["text"].startswith("Sugar is the 2nd")


def test_no_table_asks_for_one_more_photo_while_one_can_be_added():
    n = gold_scan("limca-pet-1l")["screen"]["nutrition"]
    assert n["state"] == "missing" and n["ask_photo"] and n["ask"] == "Add a photo of the nutrition table"
    assert n["text"].startswith("We didn't find a nutrition table in the photo.")
    assert screen._nutrition({"status": "missing"}, parts_sent=3)["ask_photo"] is False
    assert screen._nutrition({"status": "missing"}, catalogue={"source": "catalogue"})["ask_photo"] is False
    unclear = gold_scan("britannia-treat-croissant-cocoa")["screen"]["nutrition"]
    assert unclear["text"] == "We couldn't read the nutrition table clearly." and unclear["ask_photo"]


def test_no_second_reading_says_so_and_asks_nothing():
    g = GOLD["ziggy-donut-cake-choco-vanilla"]
    n = scan(g["ingredients"], g["nutrition"], None)["screen"]["nutrition"]
    assert n["state"] == "unverified" and n["rows"] == [] and not n["ask_photo"]


def test_some_numbers_dropped_says_so():
    t = copy.deepcopy(ZIGGY["nutrition"])
    n = scan(ZIGGY["ingredients"], t, printed(t).replace("20.26", "20.2 6"))["screen"]["nutrition"]
    assert n["state"] == "partial" and n["text"].startswith("We couldn't read the nutrition table clearly, so some")
    assert "added_sugars" not in {r["key"] for r in n["rows"]}


@pytest.mark.parametrize("name", sorted(GOLD))
def test_information_only_and_the_wording_lint(name):
    g = GOLD[name]
    without = scan(g["ingredients"], None, printed(g["nutrition"]), g["product"].get("net_quantity"))
    with_ = gold_scan(name)
    assert with_["verdict"] == without["verdict"] and with_["allergens"] == without["allergens"]
    a, b = with_["screen"], without["screen"]
    assert a["summary"] == b["summary"] and a["people"] == b["people"] and a["alerts"] == b["alerts"]
    assert_clean(list(strings(a["nutrition"])), f"nutrition {name}")

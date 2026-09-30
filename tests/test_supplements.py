"""
D-139 phase 2: a health supplement's own checks (lenses/nutra.py, data/nutra_*.json),
built in lenses/screen.py.

Pinned here: the tables carry their source and page and pass the wording lint; a
day's amounts sit beside ICMR-NIN's RDA for men and for women and are never called
a limit (Sushil, 2026-09-30), with a tile only above ICMR-NIN's upper limit; no
number is shown that the second reading of the photo doesn't have (as D-133); the
5(12) statements are "not found" only on a complete read of both faces; an additive
is "not found in the lists", never "not permitted"; a plant's note shows only for the
part it belongs to; the protein-powder note is ICMR-NIN's own sentences with the page.
Invented labels: a multivitamin tablet, a protein powder, a gummy.
"""
import copy
import json

import pytest
from test_pack_kind import reading, run, st
from test_wording import assert_clean, strings

from insidelabel.extraction.providers import cloud_vision as cv
from insidelabel.extraction.providers import gemini, prompt
from insidelabel.lenses import nutra, screen

ADULT = [{"ref": "me", "age": "adult", "avoid": ["milk"]}]
WITH_TODDLER = ADULT + [{"ref": "p1", "age": "toddler", "avoid": []}]


def scan(v, text, profiles=ADULT):
    """/scan with a second reading of the back photo (Cloud Vision stood in by `text`)."""
    with cv.replaying({cv.digest(b"\x89PNG back"): text, cv.digest(b"\x89PNG front"): "front"}):
        return run(v, profiles=profiles)


def comp(basis, *rows):
    return {"status": "read", "basis": basis, "rows": [{"name": n, "amount": a, "rda_percent": None} for n, a in rows]}


TABLET = ["Calcium carbonate", "Ferrous fumarate", "Microcrystalline cellulose", "Magnesium stearate",
          "Colour (INS 129)", "Anticaking agent (INS 551)", "Preservative (INS 223)"]
TABLET_SAYS = [st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE"), st("Take 1 tablet twice a day"),
               st("Keep out of reach of children"), st("Not to exceed the recommended daily usage"),
               st("This product is not to be used as a substitute for a varied diet")]
TABLET_COMP = comp("Each tablet contains", ("Elemental Iron (as Ferrous fumarate)", "30 mg"),
                   ("Vitamin C", "40 mg"), ("Vitamin D3", "400 IU"), ("Zinc sulphate monohydrate", "27.5 mg"),
                   ("Folic acid", "400 mcg"), ("Vitamin D3", "10 mcg"))
TABLET_TEXT = ("INGREDIENTS: " + ", ".join(TABLET) + ". Each tablet contains Elemental Iron 30 mg Vitamin C 40 mg "
               "Vitamin D3 400 IU Zinc sulphate monohydrate 27.5 mg Folic acid 400 mcg")


def tablet(**kw):
    v = reading(TABLET, TABLET_SAYS, **kw)
    v["composition"] = copy.deepcopy(TABLET_COMP)
    return v


# ---------------------------------------------------------------- the tables

def test_every_plant_row_is_sourced_and_its_names_are_unambiguous():
    rows = nutra.PLANTS["rows"]
    assert len(rows) == 53 and len({r["row"] for r in rows}) == 48
    seen = {}
    for r in rows:
        assert r["note"] and r["usage_adult_per_day"] and r["verified_on"] == "2026-09-30", r["id"]
        assert r["fssai_basis"].startswith(f"Schedule II row {r['row']}, Annexure 1 p. ") and "page image" in r["fssai_basis"]
        assert r["part"] in r["parts_in_schedule"], r["id"]
        for name in r["names"]:
            seen.setdefault(name.lower(), set()).add(r["row"])
    assert all(len(rs) == 1 for rs in seen.values()), {n: rs for n, rs in seen.items() if len(rs) > 1}
    assert "sage" not in seen and "saral" not in seen                 # printed on two rows each: left out
    assert_clean([r["note"] for r in rows], "plant notes")


def test_the_additive_lists_are_complete_and_the_rules_have_their_sources():
    assert [r["n"] for r in nutra.ADDITIVES["tablet_capsule_syrup"]["rows"]] == list(range(1, 87))
    assert [r["n"] for r in nutra.ADDITIVES["supplements_13_6"]["rows"]] == list(range(1, 41))
    rda = {r["nutrient"]: r for r in nutra.RULES["rda"]}
    assert (rda["iron"]["rda_men"], rda["iron"]["rda_women"], rda["iron"]["tul_adult"]) == (19, 29, 45)
    assert (rda["zinc"]["rda_men"], rda["zinc"]["rda_women"], rda["zinc"]["tul_adult"]) == (17, 13.2, 40)
    assert rda["vitamin_d"]["unit"] == "IU" and rda["magnesium"]["tul_adult"] == 350
    assert "folate" not in rda and "vitamin_a" not in rda             # not compared: no conversion read
    for r in nutra.RULES["statements"]:
        assert r["ask"] and r["fssai_basis"].startswith("5(12)")
    assert_clean(list(strings({k: v for k, v in nutra.RULES.items() if k != "_meta"})), "nutra_rules")


def test_the_prompt_copies_the_composition_and_older_answers_still_parse():
    assert "12. THE COMPOSITION TABLE" in prompt.VISION_PROMPT and "composition" in prompt.VISION_RESPONSE_SCHEMA["required"]
    v = reading(["Atta"])
    hardened, _ = gemini.harden(copy.deepcopy(v), sent_front=True, sent_back=True)
    assert "composition" not in hardened                               # recorded before rule 12: parses, food
    v["composition"] = {"status": "maybe", "rows": [{"name": "Iron", "amount": "5 mg"}, {"amount": "1 mg"}]}
    hardened, corr = gemini.harden(v, sent_front=True, sent_back=True)
    assert hardened["composition"]["status"] == "unreadable" and len(hardened["composition"]["rows"]) == 1


# ---------------------------------------------------------------- usage and amounts

@pytest.mark.parametrize("text,want", [
    ("Take 1 tablet daily after meals", (1, "tablet")),
    ("Adults: 1-2 capsules twice a day", (4, "capsule")),          # the most the pack says to take
    ("One scoop (30 g) 2 times a day", (2, "scoop")),
    ("Chew 2 gummies a day", (2, "gummy")),
    ("Keep out of reach of children", None),
])
def test_a_days_usage_from_the_packs_own_line(text, want):
    u = nutra.usage({"pack_statements": [st(text)]})
    assert (u and (u["count"], u["unit"])) == want


def test_amounts_for_a_day_beside_icmr_and_only_numbers_the_second_reading_has():
    a = nutra.amounts(tablet(), TABLET_TEXT)
    rows = {r["nutrient"]: r for r in a["rows"]}
    assert a["daily"]["count"] == 2 and set(rows) == {"iron", "vitamin_c", "vitamin_d"}
    assert rows["iron"]["value"] == 60 and rows["iron"]["over_tul"]      # above ICMR-NIN's 45 mg upper limit
    assert rows["vitamin_c"]["value"] == 80 and not rows["vitamin_c"]["over_tul"]
    # Zinc sulphate's 27.5 mg is the salt, folic acid has no conversion read, vitamin D in mcg isn't IU.
    assert nutra.amounts(tablet(), TABLET_TEXT.replace("Vitamin C 40 mg", "Vitamin C 4O mg"))["rows"][1]["nutrient"] != "vitamin_c"
    assert nutra.amounts(tablet(), None)["state"] == "unverified"
    v = tablet()
    v["pack_statements"] = [s for s in v["pack_statements"] if "twice" not in s["text"]]
    per = nutra.amounts(v, TABLET_TEXT)
    assert per["daily"] is None and {r["nutrient"]: r["value"] for r in per["rows"]}["iron"] == 30


def test_the_screen_never_calls_the_rda_a_limit():
    s = scan(tablet(), TABLET_TEXT)["screen"]
    [amounts] = [x for x in s["sections"] if x["id"] == "amounts"]
    assert amounts["lines"][0] == 'A day\'s usage, as the pack says: "Take 1 tablet twice a day".'
    assert amounts["lines"][1] == ("Iron: 60 mg a day. ICMR-NIN's RDA is 19 mg a day for adult men and 29 mg for adult "
                                   "women, and its upper limit for adults is 45 mg a day.")
    assert "Vitamin D: 800 IU a day. ICMR-NIN's RDA for adults is 600 IU a day" in amounts["lines"][3]
    text = json.dumps(s).lower()
    assert "rda is a limit" not in text and "exceeds the rda" not in text and "above the rda" not in text
    [tul] = [t for t in s["tiles"] if t["id"] == "tul-iron"]
    assert tul["chip"] == "Above ICMR-NIN's upper limit for adults"
    d = s["details"]["tul-iron"]
    assert d["what_research_found"][0] == "ICMR-NIN's upper limit for adults is 45 mg a day."
    assert d["on_the_label"] == "Elemental Iron (as Ferrous fumarate): 30 mg"


# ---------------------------------------------------------------- statements

def test_statements_are_not_found_only_on_a_complete_read_of_both_faces():
    v = tablet()
    v["pack_statements"] = [x for x in v["pack_statements"] if "varied diet" not in x["text"]]
    checked = {c["id"]: c for c in nutra.statements(v, TABLET_TEXT)}
    assert not checked["varied_diet"]["found"] and checked["not_medicinal"]["found"]
    assert nutra.statements(tablet(front="not_provided"), TABLET_TEXT) is None
    s = scan(v, TABLET_TEXT)["screen"]
    [sec] = [x for x in s["sections"] if x["id"] == "statements"]
    assert sec["lines"][0] == ("FSSAI's rules for health supplements ask the label for a statement that the \"product "
                               "is not to be used as a substitute for a varied diet\". We didn't find it on the photos "
                               "of this pack.")
    s = scan(tablet(front="not_provided"), TABLET_TEXT)["screen"]
    [sec] = [x for x in s["sections"] if x["id"] == "statements"]
    assert sec["lines"] == ["We need clear photos of the whole front and back to check the statements FSSAI's rules "
                            "ask for."]


def test_a_statement_the_model_missed_is_found_in_the_second_reading():
    v = tablet()
    v["pack_statements"] = [x for x in v["pack_statements"] if "NOT FOR" not in x["text"]]
    checked = {c["id"]: c for c in nutra.statements(v, TABLET_TEXT + " NOT FOR MEDICINAL USE")}
    assert checked["not_medicinal"]["found"]


# ---------------------------------------------------------------- additives

def test_additives_against_the_list_for_their_format():
    got = {x["entry"]: x for x in nutra.additives(TABLET, "tablet_capsule_syrup")}
    assert got["Microcrystalline cellulose"]["listed"] and got["Magnesium stearate"]["listed"]
    assert got["Colour (INS 129)"]["listed"] is None                  # D&C Rules' colour list isn't read
    assert got["Anticaking agent (INS 551)"]["listed"] and got["Anticaking agent (INS 551)"]["gmp"]   # 5(4)(a)
    assert got["Preservative (INS 223)"]["listed"] is False
    assert nutra.additives(["Sodium benzoate"], "tablet_capsule_syrup")[0]["listed"]   # "Benzoic acid and its salts"
    gummy = {x["entry"]: x for x in nutra.additives(["Sugar", "Gelatin", "Pectin", "Sweetener (INS 955)",
                                                     "Acidity regulator (INS 330)"], "food")}
    assert set(gummy) == {"Sweetener (INS 955)", "Acidity regulator (INS 330)"}     # gelatin, pectin: ingredients
    assert gummy["Sweetener (INS 955)"]["listed"] and gummy["Acidity regulator (INS 330)"]["gmp"]
    s = scan(tablet(), TABLET_TEXT)["screen"]
    [t] = [t for t in s["tiles"] if t["kind"] == "additive"]
    assert t["chip"] == "Not found in FSSAI's supplement lists" and "permitted" not in json.dumps(s["details"][t["id"]])


# ---------------------------------------------------------------- plants

@pytest.mark.parametrize("entry,tile", [
    ("Lahsun (Allium sativum) bulb extract", "allium_sativum_bulb"),
    ("Allium sativum leaf", None),                                   # the note is the bulb's
    ("Garlic extract", None),                                        # no English names (D-139)
    ("Green coffee bean extract (Coffea arabica)", "coffea_arabica_seed"),   # one part only: any mention
    ("Papaya (Carica papaya) ripe fruit", None),
    ("Carica papaya unripe fruit powder", "carica_papaya_unripe_fruit"),
    ("Zingiber officinale extract", "zingiber_officinale_extract"),
    ("Zingiber officinale rhizome powder", None),
    ("Withania somnifera root extract", None),                       # no note in the schedule
])
def test_a_plants_note_shows_for_the_part_it_belongs_to(entry, tile):
    hits = [h["row"]["id"] for h in nutra.plants([entry])]
    assert hits == ([tile] if tile else [])


def test_a_plant_tile_quotes_the_note_and_puts_childrens_notes_first():
    v = reading(["Guggal (Commiphora wightii) oleoresin extract", "Kalaunji seed"], [st("HEALTH SUPPLEMENT", "front")])
    s = scan(v, "INGREDIENTS: Guggal", profiles=WITH_TODDLER)["screen"]
    assert [t["title"] for t in s["tiles"]][:2] == ["Commiphora wightii, oleoresin", "Nigella sativa, seed"]
    d = s["details"]["plant-commiphora_wightii_oleoresin"]
    assert d["what_research_found"][0] == ('FSSAI\'s schedule of plants for supplements says, for this part: '
                                           '"Not recommended for children below 5 years".')
    assert "a quarter of it" in d["what_research_found"][-1]
    assert d["sources"][0]["page"] == "Schedule II row 127, Annexure 1 p. 31"


# ---------------------------------------------------------------- children, protein, sugar

def test_the_2_to_5_line_shows_only_with_a_child_on_the_phone():
    assert "children" not in {x["id"] for x in scan(tablet(), TABLET_TEXT)["screen"]["sections"]}
    s = scan(tablet(), TABLET_TEXT, profiles=WITH_TODDLER)["screen"]
    [sec] = [x for x in s["sections"] if x["id"] == "children"]
    assert sec["lines"][0].endswith('"shall only be given under medical advice by a recognized medical doctor or '
                                    'dietician or nutritionist".')


PROTEIN = ["Whey protein concentrate (Milk)", "Cocoa powder", "Sugar", "Sucralose (INS 955)"]


def test_a_protein_powder_gets_icmr_nins_own_sentences_with_the_page():
    v = reading(PROTEIN, [st("HEALTH SUPPLEMENT", "front"), st("Mix 1 scoop (30 g) in water, twice a day")],
                name="Whey Protein Powder")
    s = scan(v, "INGREDIENTS: " + ", ".join(PROTEIN))["screen"]
    [sec] = [x for x in s["sections"] if x["id"] == "protein"]
    assert sec["lines"] == ["ICMR-NIN's dietary guidelines say: \"Consuming high level of protein, especially in the "
                            "form of protein supplement powders, is therefore not advisable.\" and \"Most athletes can "
                            "get the recommended amount of protein through food alone, without the use of "
                            "supplements.\""]
    assert sec["sources"][0]["page"] == "p. 60 (PDF p. 77)"
    assert [r["key"] for r in s["summary"]] == ["sugar"]               # a powder is a food format: sugar chip
    assert "protein" not in {x["id"] for x in scan(tablet(), TABLET_TEXT)["screen"]["sections"]}
    assert "summary" not in scan(tablet(), TABLET_TEXT)["screen"]      # a tablet: no sugar answer


def test_a_gummy_gets_the_sugar_chip_and_its_13_6_additives():
    v = reading(["Glucose syrup", "Sugar", "Gelatin", "Citric acid (INS 330)", "Vitamin C"],
                [st("Dietary Supplement", "front"), st("Chew 2 gummies a day")], name="Vitamin C Gummies")
    s = scan(v, "INGREDIENTS: Glucose syrup, Sugar")["screen"]
    assert s["summary"][0]["key"] == "sugar" and s["summary"][0]["chip"].startswith("1st")


# ---------------------------------------------------------------- the whole result

@pytest.mark.parametrize("name", ["tablet", "protein", "gummy"])
def test_invented_labels_pass_the_wording_lint_and_keep_allergens_first(name):
    v = {"tablet": tablet(), "protein": reading(PROTEIN, [st("HEALTH SUPPLEMENT", "front")], name="Whey Protein Powder"),
         "gummy": reading(["Sugar", "Gelatin"], [st("Dietary Supplement", "front")], name="Gummies")}[name]
    j = scan(v, TABLET_TEXT, profiles=WITH_TODDLER)
    s = j["screen"]
    assert list(j)[0] == "allergens" and list(s)[:3] == ["state", "people", "headline"]
    assert j["verdict"]["score"] is None and j["display"] is None
    assert_clean(list(strings(s)), f"supplement {name}")

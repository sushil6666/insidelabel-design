"""
D-139, D-140 phase 1: the kind of pack, decided by core/pack_kind.py from the words
the pack prints and its licences (prompt rule 11), never by the model and never by
the product's shape.

What is pinned here:
- An ordinary food comes out exactly as before: the six gold labels' /scan output
  is compared with tests/fixtures/pack_kind_gold_before.json, captured on
  2026-09-30 before any phase 1 change.
- Answers recorded before rule 11 (no pack_statements, no licences) parse and
  replay as food (D-092).
- Invented labels for each kind (a multivitamin tablet, a protein powder, a gummy,
  an infant formula, a cereal-based complementary food, a traditional ingredient
  mix, a hypoallergenic formula, an Ayurvedic medicine), with the allergen lines
  first on every one (D-060) and every word through the wording lint (D-042).
"""
import copy
import json
import os

import pytest
from test_nutrition import GOLD, printed
from test_nutrition import scan as table_scan
from test_wording import assert_clean, strings

from insidelabel.api import main
from insidelabel.core import pack_kind
from insidelabel.extraction.providers import gemini, prompt
from insidelabel.lenses import screen
from insidelabel.review import checker

HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = json.load(open(os.path.join(HERE, "fixtures", "pack_kind_gold_before.json"), encoding="utf-8"))
FAM = [{"ref": "me", "age": "adult", "avoid": ["peanut"]}, {"ref": "p1", "age": "toddler", "avoid": ["milk"]}]
FSSAI = {"text": "FSSAI Lic. No. 10012345678901", "face": "back"}


def st(text, face="back"):
    return {"text": text, "face": face}


def reading(ingredients, statements=(), licences=(FSSAI,), front="read", back="read", allergen=None, name="Test pack"):
    """A recorded answer with prompt rule 11's fields."""
    return {"front_status": front, "back_status": back, "ingredients_status": "read",
            "product": {"brand": "Testco", "name": name, "variant": None, "net_quantity": None,
                        "veg_mark": "veg"},
            "product_match": {"status": "match" if front == "read" else "single_image", "evidence": []},
            "front_identity": None,
            "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
            "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
            "ingredients": ingredients, "allergen_statement": allergen, "front_claims": [],
            "front_claim_footnotes": [], "extraction_notes": [],
            "confidence": {"ingredients": 0.98, "front_claims": 0.9, "product_identity": 0.8},
            "pack_statements": list(statements), "licences": list(licences)}


def run(v, profiles=FAM):
    """/scan with a recorded answer, both faces sent when the answer read both."""
    from fastapi.testclient import TestClient
    files = {"back": ("b.png", b"\x89PNG back", "image/png")}
    if v["front_status"] == "read":
        files["front"] = ("f.png", b"\x89PNG front", "image/png")
    r = TestClient(main.app).post("/scan", files=files, data={
        "replay": json.dumps(v), "profiles": json.dumps(profiles), "pairing_confirmed": "true"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- ordinary food, unchanged

@pytest.mark.parametrize("name", sorted(GOLD))
def test_the_six_gold_labels_come_out_exactly_as_before(name):
    g = GOLD[name]
    t = g["nutrition"]
    j = table_scan(g["ingredients"], t, printed(t), g["product"].get("net_quantity"), profiles=FAM)
    assert j["pack_kind"] == {"code": "food", "evidence": [], "review": []}
    for key, before in BEFORE[name].items():
        assert j[key] == before, f"{name}: {key} changed"


def test_an_answer_from_before_rule_11_parses_and_is_food():
    v = reading(["Whole wheat flour", "Salt"])
    del v["pack_statements"], v["licences"]
    hardened, _ = gemini.harden(copy.deepcopy(v), sent_front=True, sent_back=True)
    assert "pack_statements" not in hardened
    assert pack_kind.decide(hardened)["code"] == "food"
    assert gemini.OPTIONAL_KEYS >= {"pack_statements", "licences"}


def test_the_prompt_copies_statements_and_licences_and_never_classifies():
    assert "11. STATEMENTS AND LICENCES" in prompt.VISION_PROMPT
    assert "never write what kind it is yourself" in prompt.VISION_PROMPT
    # D-139: shape never decides. A tablet is read; the licences decide.
    assert "medicines)" not in prompt.VISION_PROMPT and "even when they look like a" in prompt.VISION_PROMPT
    for key in ("pack_statements", "licences"):
        assert key in prompt.VISION_RESPONSE_SCHEMA["required"]
    assert main.PROMPT_VERSION != "unchanged"


def test_a_statement_on_a_face_never_sent_moves_to_the_face_that_was():
    v = reading(["Whey protein"], [st("HEALTH SUPPLEMENT", "front"), {"text": "  ", "face": "back"}, "junk"])
    hardened, corrections = gemini.harden(v, sent_front=False, sent_back=True)
    assert hardened["pack_statements"] == [{"text": "HEALTH SUPPLEMENT", "face": "back"}]
    assert any("pack_statements face 'front' -> back" in c for c in corrections)


# ---------------------------------------------------------------- the rule

@pytest.mark.parametrize("statements,code", [
    ([st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE")], "supplement"),
    ([st("Nutraceutical", "front")], "supplement"),
    ([st("Dietary Supplement", "front")], "supplement"),
    ([st("IMPORTANT NOTICE", "front"), st("MOTHER’S MILK IS BEST FOR YOUR BABY", "front")], "infant"),
    ([st("Processed Cereal Based Complementary Food")], "infant"),
    ([st("Traditional Food for Infants", "front")], "infant"),
    ([st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"), st("HYPOALLERGENIC FORMULA", "front"),
      st("RECOMMENDED TO BE TAKEN UNDER MEDICAL ADVICE ONLY")], "special_medical"),
    ([st("FOOD FOR SPECIAL MEDICAL PURPOSE", "front")], "special_medical"),
    ([st("NOT FOR MEDICINAL USE")], "food"),            # supporting only, alone it decides nothing
    ([st("Store in a cool, dry place")], "food"),
])
def test_the_printed_words_decide(statements, code):
    assert pack_kind.decide(reading(["x"], statements))["code"] == code


def test_a_company_name_or_an_ingredient_is_not_a_kind():
    v = reading(["Vitamin premix (Food supplement grade)"], [st("Marketed by Testco Nutraceuticals Pvt Ltd")])
    v["back_identity"]["manufacturer"] = "Testco Nutraceuticals Pvt Ltd"
    v["product"]["brand"] = "Testco Nutraceuticals"
    assert pack_kind.decide(v)["code"] == "food"             # a company, an ingredient, a brand: never a kind
    v["pack_statements"].append(st("HEALTH SUPPLEMENT", "front"))
    assert pack_kind.decide(v)["code"] == "supplement"


def test_licences_decide_before_words_and_only_on_a_complete_read():
    drug = [{"text": "Ayurvedic Medicine Mfg. Lic. No. A-2755", "face": "back"}]
    k = pack_kind.decide(reading(["Tulsi", "Mulethi"], [st("Tulsi Mulethi", "front")], licences=drug))
    assert k["code"] == "not_food" and k["evidence"][0]["text"] == drug[0]["text"]
    # An FSSAI licence decides "food" whatever else is printed (D-116).
    both = drug + [FSSAI]
    assert pack_kind.decide(reading(["Tulsi"], licences=both))["code"] == "food"
    # The 14-digit number counts as FSSAI's even without the word.
    assert pack_kind.decide(reading(["Tulsi"], licences=drug + [st("Lic. No. 10019022001234")]))["code"] == "food"
    # Back only: the licence may be on the front. Never not_food; a reviewer looks.
    k = pack_kind.decide(reading(["Tulsi"], licences=drug, front="not_provided"))
    assert k["code"] == "food" and "not both faces were read" in k["review"][0]


def test_the_catalogue_category_and_disagreements():
    assert pack_kind.decide({}, category="13.6")["code"] == "supplement"
    assert pack_kind.decide({}, category="13.1.3")["code"] == "special_medical"
    assert pack_kind.decide({}, category="13.1.1")["code"] == "infant"
    assert pack_kind.decide({}, category="13.2")["code"] == "infant"
    assert pack_kind.decide({}, category="7.2.1")["code"] == "food"
    k = pack_kind.decide(reading(["x"], [st("HEALTH SUPPLEMENT", "front")]), category="7.2.1")
    assert k["code"] == "supplement" and "category 7.2.1" in k["review"][0]
    k = pack_kind.decide(reading(["x"]), category="13.6")
    assert k["code"] == "supplement" and k["evidence"][0]["rule"] == "catalogue_category"


def test_every_phrase_in_the_table_has_a_basis_and_a_date():
    for row in pack_kind.TABLE["words"] + pack_kind.TABLE["supporting"]:
        assert row["basis"] and row["verified_on"] == "2026-09-30", row["id"]
        for phrase in row["phrases"]:
            assert phrase == pack_kind.norm(phrase).strip(), phrase     # stored already normalised
    assert set(pack_kind.TABLE["kinds"]) == {"food", "supplement", "infant", "special_medical", "not_food"}
    for code, parts in pack_kind.PARTS.items():
        assert parts[0] == "people", code                              # D-060: allergens first, every kind


# ---------------------------------------------------------------- the result per kind

INVENTED = {
    "multivitamin_tablet": (["Calcium carbonate", "Magnesium oxide", "Microcrystalline cellulose", "Ferrous fumarate",
                             "Colour (INS 129)", "Hydrogenated vegetable oil", "Soy lecithin"],
                            [st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE"),
                             st("Take 1 tablet daily after meals"), st("Keep out of reach of children")],
                            "supplement"),
    "protein_powder": (["Whey protein concentrate (Milk)", "Cocoa powder", "Sucralose (INS 955)", "Xanthan gum (INS 415)"],
                       [st("HEALTH SUPPLEMENT", "front"), st("1 scoop (30 g) twice a day")], "supplement"),
    "gummy": (["Glucose syrup", "Sugar", "Gelatin", "Citric acid (INS 330)", "Vitamin C"],
              [st("Dietary Supplement", "front"), st("Not recommended for children below 4 years")], "supplement"),
    "infant_formula": (["Milk solids", "Lactose", "Vegetable oils", "Minerals", "Vitamins"],
                       [st("IMPORTANT NOTICE", "front"), st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"),
                        st("Infant Formula", "front")], "infant"),
    "cereal_complementary": (["Wheat flour", "Milk solids", "Sugar", "Minerals", "Vitamins"],
                             [st("MOTHER'S MILK IS BEST FOR YOUR BABY", "front"),
                              st("Infant food shall be introduced only after the age of six months and up to the age of two years"),
                              st("Processed Cereal Based Complementary Food", "front")], "infant"),
    "traditional_mix": (["Ragi flour", "Moong dal", "Jaggery", "Cardamom"],
                        [st("Traditional Food for Infants", "front")], "infant"),
    "hypoallergenic": (["Extensively hydrolysed whey protein", "Maltodextrin", "Vegetable oils"],
                       [st("HYPOALLERGENIC FORMULA", "front"),
                        st("RECOMMENDED TO BE TAKEN UNDER MEDICAL ADVICE ONLY", "front")], "special_medical"),
}


@pytest.mark.parametrize("name", sorted(INVENTED))
def test_each_kind_shows_allergens_first_and_nothing_that_judges_it_as_food(name):
    ingredients, statements, code = INVENTED[name]
    j = run(reading(ingredients, statements, allergen="Contains milk, soy."))
    s = j["screen"]
    assert j["pack_kind"]["code"] == code and list(j)[0] == "allergens"
    assert list(s)[:3] == ["state", "people", "headline"] and s["people"]         # D-060
    assert s["kind"]["code"] == code and s["parts"] == list(pack_kind.parts(code))
    for absent in ("summary", "tiles", "details", "additives", "glance", "tallies", "ingredient_notes",
                   "nutrition", "band", "shop_list", "alerts", "additive_alert", "worth_knowing"):
        assert absent not in s, (name, absent)
    assert s["ingredients"] == ingredients
    assert ("breastfeeding" in s) == (code == "infant")
    assert_clean(list(strings(s)), f"screen {name}")


def test_the_words_of_each_kind():
    ingredients, statements, _ = INVENTED["multivitamin_tablet"]
    s = run(reading(ingredients, statements))["screen"]
    assert s["headline"]["text"] == 'This pack says "HEALTH SUPPLEMENT".'
    assert s["kind"]["lines"] == [screen.KIND_TEXT["supplement"]]
    assert {"text": "NOT FOR MEDICINAL USE", "face": "back"} in s["kind"]["evidence"]
    s = run(reading(*INVENTED["infant_formula"][:2]))["screen"]
    assert s["headline"]["text"] == "This is a food for infants."
    assert s["breastfeeding"]["text"].startswith("ICMR-NIN's dietary guidelines say: \"Ensure exclusive breastfeeding")
    assert s["breastfeeding"]["sources"][0]["page"] == "p. 21 (PDF p. 38)"


def test_a_pack_that_isnt_food_quotes_its_licence_and_the_act():
    drug = [{"text": "Ayurvedic Medicine Mfg. Lic. No. A-2755", "face": "back"}]
    j = run(reading(["Tulsi", "Mulethi", "Honey"], [st("Tulsi Mulethi Syrup", "front")], licences=drug))
    s = j["screen"]
    assert j["pack_kind"]["code"] == "not_food"
    assert s["headline"]["text"] == "We didn't find an FSSAI licence number on the photos."
    assert s["kind"]["lines"][0] == 'The pack prints "Ayurvedic Medicine Mfg. Lic. No. A-2755".'
    assert "section 3(1)(j)" in s["kind"]["lines"][1] and s["kind"]["sources"][0]["page"] == "PDF p. 2"
    assert s["people"][0]["ref"] == "me"
    assert_clean(list(strings(s)), "not_food")


def test_the_same_pack_without_rule_11_is_scored_as_before():
    # Information only for food: the verdict itself never depends on the kind.
    ingredients, statements, _ = INVENTED["gummy"]
    with_kind = run(reading(ingredients, statements))
    without = run(reading(ingredients, []))
    assert with_kind["verdict"] == without["verdict"] and with_kind["allergens"] == without["allergens"]
    assert without["pack_kind"]["code"] == "food" and "summary" in without["screen"]


# ---------------------------------------------------------------- review

def test_the_review_checker_sends_every_kind_but_food_to_a_person():
    draft = {"ingredients": ["Whey protein"], "category": "13.6", "name": "Whey"}
    v = reading(["Whey protein"], [st("HEALTH SUPPLEMENT", "front")])
    [c] = [c for c in checker.check(draft, {"kind": "new_product", "raw": v}) if c["check"] == "pack_kind"]
    assert not c["ok"] and "the pack reads as supplement" in c["detail"]
    [c] = [c for c in checker.check({**draft, "category": "7.2.1"}, {"kind": "new_product", "raw": reading(["Atta"])})
           if c["check"] == "pack_kind"]
    assert c["ok"]
    [c] = [c for c in checker.check({**draft, "category": "13.6"}, {"kind": "new_product", "raw": reading(["Atta"])})
           if c["check"] == "pack_kind"]
    assert not c["ok"] and "category 13.6" not in c["detail"]      # the category itself gives the kind


def test_the_app_renders_the_kind_and_keeps_it_out_of_compare():
    src = open(os.path.join(os.path.dirname(HERE), "web", "app.js"), encoding="utf-8").read()
    assert "if (s.kind) {" in src and "function kindView(s)" in src
    assert '(!body.screen.parts || body.screen.parts.includes("compare"))' in src

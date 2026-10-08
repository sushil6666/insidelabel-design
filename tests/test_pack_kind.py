"""
D-139, D-140 phase 1: the kind of pack, decided by core/pack_kind.py from the words
the pack prints and its licences (prompt rule 11), never by the model and never by
the product's shape.

What is pinned here:
- An ordinary food comes out exactly as before: the six gold labels' /scan output
  is compared with tests/fixtures/pack_kind_gold_before.json, captured on
  2026-09-30 before any phase 1 change.
  Its `technical` lines were reworded on 2026-10-04 (no file names, table keys or
  source codes shown to users); every other value is as captured.
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
from insidelabel.reliability import gates
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
        got = j[key]
        if key == "screen":
            # D-140 part 5: FAM's toddler profile is asked once whether the child is under 2.
            # That question is the only addition; everything captured before is unchanged.
            assert got["band_question"]["refs"] == ["p1"]
            got = {k: v for k, v in got.items() if k != "band_question"}
            # D-173's follow-up to D-111: the scope line and "other ingredients" count the list's
            # printed entries (were the engine's parsed parts); one sentence says what was checked.
            n = len(got["ingredients"])                  # the entries the screen lists (and the glance ring)
            assert got["checked"] is None and got["scope"].startswith(f"We checked the {n} ingredients on the list ")
            assert got["ordinary"]["count"] == got["glance"]["counts"].get("other", 0) < before["ordinary"]["count"]
            got = {k: v for k, v in got.items() if k not in ("checked", "scope")}
            got["ordinary"] = {k: v for k, v in got["ordinary"].items() if k not in ("count", "text")}
            before = {k: v for k, v in before.items() if k not in ("checked", "scope")}
            before["ordinary"] = {k: v for k, v in before["ordinary"].items() if k not in ("count", "text")}
            # D-177: each nutrition row carries the numbers its bar is drawn from; its words are unchanged.
            # D-185 Phase 2: and its own sentence cut in two (amount, why); `text` is still the whole.
            if got.get("nutrition"):
                got["nutrition"] = {**got["nutrition"], "rows": [{k: v for k, v in r.items() if k not in ("bar", "amount", "why")}
                                                                for r in got["nutrition"]["rows"]]}
        if key == "disclosures":
            # D-173's follow-up to D-165: "What this check covers" no longer speaks of a score.
            old = [d for d in before if "not part of the score" in d]
            assert len(old) == 1 and gates.ALWAYS_DISCLOSE[0] in got
            before = [gates.ALWAYS_DISCLOSE[0] if d in old else d for d in before]
        assert got == before, f"{name}: {key} changed"


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


# D-187 (item #82, Bambino Vermicelli POPULAR 850 g): the FSSAI logo is artwork, so the
# model copied only "Lic No." and a number whose end was under the shopper's thumb.
ITEM_82 = [st("Lic No. 100140470002"), st("Lic No. 11423999000016")]
TABLE_READ = {"status": "read", "per_100_basis": "100 g", "rda_column": None, "serving_size": None,
              "servings_per_pack": None, "rows": [{"nutrient": "Energy", "unit": "kcal", "per_100": "350",
                                                   "per_serving": None, "rda_percent": None}]}
CHYAWANPRASH = [st("Ayurvedic Proprietary Medicine Mfg Lic No. 25D/12/86 AYUSH")]


def item_82(licences=ITEM_82, nutrition=TABLE_READ):
    v = reading(["Wheat semolina"], [st("Product: Vermicelli (Sevai/Semia)")], licences=licences,
                name="Vermicelli")
    if nutrition:
        v["nutrition"] = nutrition
    return v


def test_item_82_a_plain_lic_no_is_food():
    k = pack_kind.decide(item_82(), category="6.4.2")
    assert k["code"] == "food" and k["review"] == []
    # The 12-digit line alone: a probable FSSAI licence, its end not read. Food, and a reviewer looks.
    for v in (item_82([ITEM_82[0]]), item_82([ITEM_82[0]], nutrition=None)):
        for cat in ("6.4.2", None):
            k = pack_kind.decide(v, category=cat)
            assert k["code"] == "food" and k["licences"]["probable"] == [ITEM_82[0]]
            assert k["review"] == [f'{pack_kind.PROBABLE_NOTE} ("Lic No. 100140470002")']
    # A plain "Lic No." with no number like FSSAI's names no licence at all: nothing to say.
    for text in ("Lic No. 4471", "Licence No. ABC/12", "Reg No. 77/2020", "License no 55"):
        k = pack_kind.decide(reading(["Wheat"], licences=[st(text)]))
        assert k["code"] == "food" and k["review"] == [] and k["licences"]["other"] == [], text
    # The number must look like FSSAI's: 10 to 13 digits starting 1 or 2.
    assert pack_kind.licences({"licences": [st("Lic No. 300140470002")]})["probable"] == []
    assert pack_kind.licences({"licences": [st("Lic No. 100140470")]})["probable"] == []
    assert pack_kind.licences({"licences": [st("Lic No. 2001404700")]})["probable"] != []


def test_a_medicine_licence_still_gives_not_food_on_a_complete_read():
    k = pack_kind.decide(reading(["Amla", "Ghee", "Honey"], licences=CHYAWANPRASH))
    assert k["code"] == "not_food" and k["evidence"][0]["text"] == CHYAWANPRASH[0]["text"]
    for text in ("AYUSH Lic. No. AUS-1234", "Drug Licence No. 20B/45", "D.L. No. KA-123", "DL No. 45/77"):
        assert pack_kind.decide(reading(["Amla"], licences=[st(text)]))["code"] == "not_food", text
    # "Ayurvedic" or "AYUSH" counts only beside a licence.
    assert pack_kind.decide(reading(["Amla"], [st("Ayurvedic recipe", "front")], licences=()))["code"] == "food"
    # D-139, unchanged: a partial read never gives not_food.
    k = pack_kind.decide(reading(["Amla"], licences=CHYAWANPRASH, front="not_provided"))
    assert k["code"] == "food" and "not both faces were read" in k["review"][0]


def test_an_ordinary_food_signal_overrules_the_licence_rule_alone():
    # A nutrition table, or an ordinary food category: a reviewer looks, never not_food.
    v = reading(["Amla"], licences=CHYAWANPRASH)
    v["nutrition"] = TABLE_READ
    k = pack_kind.decide(v)
    assert k["code"] == "food" and "the pack shows a nutrition table" in k["review"][0]
    k = pack_kind.decide(reading(["Amla"], licences=CHYAWANPRASH), category="6.4.2")
    assert k["code"] == "food" and "category 6.4.2, an ordinary food category" in k["review"][0]
    v["nutrition"] = {**TABLE_READ, "status": "not_found"}
    assert pack_kind.decide(v)["code"] == "not_food"
    # A 13.x category is not an ordinary food signal; the clash goes to a reviewer as before.
    k = pack_kind.decide(reading(["Amla"], licences=CHYAWANPRASH), category="13.6")
    assert k["code"] == "not_food" and "category 13.6 is supplement" in k["review"][0]


def test_the_review_checker_sends_item_82_to_a_person_for_its_licence():
    draft = {"ingredients": ["Wheat semolina"], "category": "6.4.2", "name": "Vermicelli"}
    [c] = [c for c in checker.check(draft, {"kind": "new_product", "raw": item_82([ITEM_82[0]])})
           if c["check"] == "pack_kind"]
    assert not c["ok"] and "probable FSSAI licence, last digits not read" in c["detail"]
    assert "not_food" not in c["detail"]
    [c] = [c for c in checker.check(draft, {"kind": "new_product", "raw": item_82()}) if c["check"] == "pack_kind"]
    assert c["ok"]


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
    # D-139 phase 2: a supplement has its own tiles and sections (and a sugar chip in a food format).
    own = {"tiles", "details", "summary"} if code == "supplement" else set()
    for absent in {"summary", "tiles", "details", "additives", "glance", "tallies", "ingredient_notes",
                   "nutrition", "band", "shop_list", "alerts", "additive_alert", "worth_knowing"} - own:
        assert absent not in s, (name, absent)
    assert s["ingredients"] == ingredients
    assert "breastfeeding" not in s                      # D-140: held until the lawyer answers
    assert_clean(list(strings(s)), f"screen {name}")


def test_the_words_of_each_kind():
    ingredients, statements, _ = INVENTED["multivitamin_tablet"]
    s = run(reading(ingredients, statements))["screen"]
    assert s["headline"]["text"] == 'This pack says "HEALTH SUPPLEMENT".'
    assert s["kind"]["lines"] == [screen.KIND_TEXT["supplement"]]
    assert {"text": "NOT FOR MEDICINAL USE", "face": "back"} in s["kind"]["evidence"]
    s = run(reading(*INVENTED["infant_formula"][:2]))["screen"]
    # The kind in the pack's own words: the product's name for it before the notice.
    assert s["headline"]["text"] == 'This pack says "Infant Formula".'
    assert s["kind"]["lines"] == ["Results for infant foods aren't shown yet. We show the allergens on the list "
                                  "and the ingredient list."]
    assert "breastfeeding" not in s
    k = pack_kind.decide({}, category="13.2")
    s = screen._kind_screen(k, people=[], ingredients=["Rice"], reliability={})
    assert s["headline"]["text"] == "Filed in our catalogue as a food for infants."


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
    # The engine's reading is the same; a supplement's score, grade and band aren't sent (D-139 phase 2).
    assert with_kind["verdict"]["flags"] == without["verdict"]["flags"] and with_kind["allergens"] == without["allergens"]
    assert with_kind["verdict"]["score"] is None and without["verdict"]["score"] is not None
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


# ---------------------------------------------------------------- D-140: the server refuses, not only the app

def test_scan_withholds_every_result_field_for_an_infant_pack():
    from fastapi.testclient import TestClient
    v = reading(*INVENTED["cereal_complementary"][:2])
    v["front_claims"] = ["No added preservatives"]
    r = TestClient(main.app).post("/scan", files={"back": ("b.png", b"\x89PNG back", "image/png"),
                                                  "front": ("f.png", b"\x89PNG front", "image/png")},
                                  data={"replay": json.dumps(v), "profiles": json.dumps(FAM),
                                        "pairing_confirmed": "true", "compare_regulators": "true"})
    j = r.json()
    for field in ("verdict", "display", "claim_check", "nutrition", "regulators"):
        assert j[field] is None, field                              # no score, grade, band or other result
    assert j["withheld"] == {"fields": ["verdict", "display", "claim_check", "nutrition", "regulators"],
                             "reason": "infant_in_shadow"}
    assert list(j)[0] == "allergens" and j["allergens"] and j["screen"]["people"]
    assert "score" not in json.dumps(j["screen"]) and "grade" not in json.dumps(j["screen"])
    # A supplement keeps its flags but no score (D-139 phase 2); food keeps everything.
    sup = run(reading(*INVENTED["multivitamin_tablet"][:2]))
    assert sup["verdict"]["score"] is None and sup["verdict"]["flags"] and sup["display"] is None
    assert sup["withheld"]["reason"] == "supplement_not_scored"
    assert "withheld" not in run(reading(["Atta", "Salt"]))


def _compare(packs):
    from fastapi.testclient import TestClient
    return TestClient(main.app).post("/compare", json={"packs": packs, "age": "kid"})


FOOD_A = {"id": "a", "name": "Atta biscuit", "ingredients": ["Whole wheat flour", "Sugar"]}
FOOD_B = {"id": "b", "name": "Rusk", "ingredients": ["Refined wheat flour", "Sugar", "Palm oil"]}


def test_compare_refuses_an_infant_pack_the_client_reports():
    r = _compare([FOOD_A, {**FOOD_B, "kind": "infant"}])
    assert r.status_code == 422
    body = {k: v for k, v in r.json().items() if k != "request_id"}     # the app's error shape, flattened
    assert body == {"error": "not_comparable", "reason": "infant_food", "pack": "b",
                    "detail": "We don't compare or rank foods for infants."}


def test_compare_refuses_an_infant_pack_from_its_printed_words_whatever_kind_the_client_says():
    words = [{"text": "MOTHER'S MILK IS BEST FOR YOUR BABY", "face": "front"}]
    r = _compare([FOOD_A, {**FOOD_B, "kind": "food", "pack_statements": words}])
    assert r.status_code == 422 and r.json()["reason"] == "infant_food"


def test_compare_refuses_a_supplement_until_phase_2_and_still_ranks_food():
    r = _compare([FOOD_A, {**FOOD_B, "pack_statements": [{"text": "HEALTH SUPPLEMENT", "face": "front"}]}])
    assert r.status_code == 422 and r.json()["reason"] == "supplement"
    r = _compare([FOOD_A, FOOD_B])                                  # older clients send no kind: food
    assert r.status_code == 200 and r.json()["outcome"] in ("best", "tie", "no_clear_pick", "unknown_additives")


def test_no_shop_list_for_an_infant_pack_read_from_a_screen():
    ingredients, statements, _ = INVENTED["infant_formula"]
    v = reading(ingredients, statements, front="not_provided")
    v["image_content"] = {"back": "screen", "front": "not_provided"}
    s = run(v)["screen"]
    assert s["kind"]["code"] == "infant" and "from_screen" in s and "shop_list" not in s
    v = reading(["Atta", "Salt"], front="not_provided")
    v["image_content"] = {"back": "screen", "front": "not_provided"}
    assert run(v)["screen"]["shop_list"] is True                    # food read from a screen: as D-130


def test_no_ranking_part_for_an_infant_pack():
    # The only ranking the product has is /compare's better pick (refused above); the
    # screen carries no score, band, summary chips or "Your scans" tallies for one.
    parts = pack_kind.parts("infant")
    for part in ("compare", "shop_list", "tallies", "score", "summary", "tiles"):
        assert part not in parts
    assert pack_kind.COMPARABLE == {"food"}


def test_the_replay_tool_lists_item_82_as_changed():
    # D-092, D-187: tools/pack_kind_replay.py replays decide() on stored answers.
    import importlib.util
    spec = importlib.util.spec_from_file_location("pack_kind_replay", os.path.join(HERE, "..", "tools", "pack_kind_replay.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    row = {"id": 1, "status": "pending_review", "barcode": "8904287001052", "name": "Vermicelli",
           "category_code": "6.4.2", "review_items": "82 open", "pack_kind": "not_food",
           "pack_kind_evidence": {"evidence": [], "review": []}, "raw_extraction": item_82([ITEM_82[0]])}
    [r] = tool.replay([row])
    assert r["changed"] and r["was"] == "not_food" and r["now"] == "food"
    [r] = tool.replay([{**row, "pack_kind": "food", "raw_extraction": reading(["Wheat"])}])
    assert not r["changed"]

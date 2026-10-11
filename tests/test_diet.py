"""
D-198: two diet choices in the avoid list, "Vegetarian only" and "No onion or garlic"
(Sushil, 2026-10-11). Labels are invented but read like real Indian packs.
"""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from insidelabel.api import main
from insidelabel.core import tokenize
from insidelabel.lenses import diet
from insidelabel.lenses import screen

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
ME = [{"ref": "me", "age": "adult", "avoid": ["vegetarian", "no_onion_garlic"]}]


def answer(ingredients, mark="veg", status="read", conf=0.98, name="Sample pack"):
    return {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": status,
        "product": {"brand": "Sample", "name": name, "variant": None, "net_quantity": "100 g", "veg_mark": mark},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [],
        "extraction_notes": [], "confidence": {"ingredients": conf, "front_claims": 0.0, "product_identity": 0.9},
    }


def scan(ingredients, profiles=ME, **kw):
    r = c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
               data={"replay": json.dumps(answer(ingredients, **kw)), "profiles": json.dumps(profiles)})
    assert r.status_code == 200, r.text
    return r.json()


def one(j, ref="me"):
    return next((p for p in j["screen"]["people"] if p["ref"] == ref), None)


def quiet(j, ref="me"):
    return next((r["lines"] for r in j["screen"].get("for_you", []) if r["ref"] == ref), [])


def states(ingredients, mark="veg", **kw):
    return {k: r.state for k, r in diet.check(ingredients, list(diet.DIETS), veg_mark=mark, **kw).items()}


# ------------------------------------------------------------------ the rules

def test_vegetarian_matches_from_the_regulation_and_jecfa():
    assert states(["Sugar", "Gelatine"])["vegetarian"] == "contains"
    assert states(["Sugar", "Gelling Agent (INS 441)"])["vegetarian"] == "contains"
    assert states(["Colour (INS 120)"])["vegetarian"] == "contains"
    assert states(["Preservative (1105)"])["vegetarian"] == "contains"
    assert states(["Refined Wheat Flour", "Egg Powder (3%)"])["vegetarian"] == "contains"       # 2(1)(o): eggs
    assert states(["Rice", "Chicken (12%)"])["vegetarian"] == "contains"


def test_milk_honey_and_the_waxes_are_not_counted():
    # Reg. 2(1)(o): "does not include milk, milk products, honey or bees wax or carnauba wax or shellac".
    assert states(["Milk Solids", "Ghee", "Honey", "Glazing Agent (INS 904)", "Beeswax", "Paneer"])["vegetarian"] \
        == "not_listed"
    assert states(["Eggless Cake Premix"])["vegetarian"] == "not_listed"


def test_an_additive_of_either_origin():
    assert states(["Wheat Flour", "Emulsifier (471)"], mark="not_visible")["vegetarian"] == "uncertain"
    assert states(["Emulsifier (322)"], mark=None)["vegetarian"] == "uncertain"
    assert states(["Emulsifier (471 - vegetable origin)"], mark=None)["vegetarian"] == "not_listed"
    assert states(["Emulsifier (Soya Lecithin, 322)"], mark=None)["vegetarian"] == "not_listed"
    r = diet.check(["Emulsifier (471)"], ["vegetarian"], veg_mark="not_visible")["vegetarian"]
    assert diet.text(r) == "INS 471 can be made from plant or animal fat; the label doesn't say which."


def test_a_flavour_named_after_meat_is_amber_not_red():
    r = diet.check(["Noodles", "Chicken Flavour (Nature Identical)"], ["vegetarian"], veg_mark="veg")["vegetarian"]
    assert r.state == "uncertain"
    assert diet.text(r) == ("We can't tell whether \"Chicken Flavour (Nature Identical)\" is made from chicken; "
                            "the label doesn't say.")


def test_the_brown_mark_is_red_even_on_a_partial_read():
    assert states(["Rice", "Salt"], mark="non_veg")["vegetarian"] == "contains"
    assert states(["Rice"], mark="non_veg", complete=False)["vegetarian"] == "contains"
    r = diet.check(["Maida", "Egg Powder (3%)"], ["vegetarian"], veg_mark="non_veg")["vegetarian"]
    assert diet.words(r) == ("The pack has the brown non-vegetarian mark.", "Egg is listed: \"Egg Powder (3%)\".")
    assert diet.words(r, "pack")[0] == "The pack we checked has the brown non-vegetarian mark."


def test_onion_and_garlic():
    assert states(["Potatoes", "Onion Powder"])["no_onion_garlic"] == "contains"
    assert states(["Garlic Paste"])["no_onion_garlic"] == "contains"
    assert states(["Lahsun"])["no_onion_garlic"] == "contains"
    assert states(["Spring Onion Flakes"])["no_onion_garlic"] == "contains"
    assert states(["Gram Flour", "Spices"])["no_onion_garlic"] == "uncertain"
    assert states(["Masala"])["no_onion_garlic"] == "uncertain"
    assert states(["Spices (Chilli, Cumin)"])["no_onion_garlic"] == "not_listed"     # named, part by part
    assert states(["Spices (Chilli, Garlic)"])["no_onion_garlic"] == "contains"
    assert states(["Asafoetida (Hing)"])["no_onion_garlic"] == "not_listed"           # hing is not onion
    assert states(["Onion Seeds (Kalonji)"])["no_onion_garlic"] == "not_listed"       # nigella
    r = diet.check(["Spices"], ["no_onion_garlic"])["no_onion_garlic"]
    assert diet.text(r) == ("The list says \"Spices\" without naming what's in it, so we can't tell if it includes "
                            "onion or garlic.")


def test_below_095_or_partial_is_cannot_confirm():
    assert set(states(["Onion"], confidence=0.9).values()) == {"cannot_confirm"}
    assert set(states(["Onion"], complete=False).values()) == {"cannot_confirm"}
    assert set(states(["Onion"], reliable=False).values()) == {"cannot_confirm"}


def test_every_ins_number_goes_through_the_one_parser(monkeypatch):
    # D-099: diet.py asks core/tokenize.py, never a pattern of its own.
    seen = []
    real = tokenize.ins_numbers
    monkeypatch.setattr(tokenize, "ins_numbers", lambda t: seen.append(t) or real(t))
    diet.check(["Emulsifier (471)"], ["vegetarian"])
    assert seen == ["Emulsifier (471)"]


def test_exempt_products_carry_no_mark(monkeypatch):
    # Reg. 5(4)(d) (advisor, 2026-10-11): no mark is expected, so a missing one is not a finding.
    assert diet.mark_exempt("Forest Honey", ["Honey"])
    assert diet.mark_exempt("Packaged Drinking Water", ["Water", "Added Minerals (Magnesium Sulphate)"])
    assert diet.mark_exempt(None, ["Toned Milk"])
    assert not diet.mark_exempt("Honey Oats", ["Rolled Oats", "Honey (5%)"])
    r = diet.check(["Honey"], ["vegetarian"], veg_mark="not_visible", product_name="Wild Forest Honey")["vegetarian"]
    assert diet.mark_note(r) is None
    r = diet.check(["Oats"], ["vegetarian"], veg_mark="not_visible", product_name="Oats")["vegetarian"]
    assert diet.mark_note(r) == diet.NO_MARK["photo"]


def test_the_data_cites_its_sources():
    veg = diet.DIETS["vegetarian"]
    assert "Compendium_Labelling_Display_23_09_2021.pdf" in veg["basis"]["document"]
    assert veg["basis"]["non_vegetarian"].startswith("Reg. 2(1)(o), PDF page 3:")
    assert veg["basis"]["vegetarian"].startswith("Reg. 2(1)(v), PDF page 4:")
    assert veg["basis"]["brown_mark"].startswith("Reg. 5(4)(a), PDF page 14:")
    assert veg["basis"]["exempt"].startswith("Reg. 5(4)(d), PDF page 15:")
    for row in veg["ins"]:
        assert row["source"].startswith("JECFA") and row["fssai_basis"] and row["verified_on"]


# ------------------------------------------------------------------ /scan

def test_allergens_stay_first_and_diet_comes_next():
    j = scan(["Sugar", "Gelatine"], profiles=[{"ref": "me", "age": "adult", "avoid": ["milk", "vegetarian"]}])
    assert list(j)[:3] == ["allergens", "diet", "screen"]
    assert j["allergens"]["avoid"] == ["milk"]                                  # unchanged, D-060
    assert [r["code"] for r in j["allergens"]["results"]] == ["milk"]
    assert j["diet"]["avoid"] == ["vegetarian"] and j["diet"]["veg_mark"] == "veg"


def test_only_diet_codes_leave_allergens_null():
    j = scan(["Sugar"], profiles=[{"ref": "me", "age": "adult", "avoid": ["no_onion_garlic"]}])
    assert j["allergens"] is None and j["diet"]["results"][0]["state"] == "not_listed"
    assert scan(["Sugar"], profiles=[])["diet"] is None


def test_gelatin_with_the_green_mark_is_red_quoting_both():
    j = scan(["Sugar", "Water", "Gelatine"], mark="veg")
    p = one(j)
    assert p["status"] == "contains" and p["line"] == "Gelatin is listed: \"Gelatine\"."
    assert p["more"] == "It comes from animal collagen (skin and bones). The pack also has the green vegetarian mark."
    assert p["share"].startswith("For you, gelatin is listed")


def test_ins_441_without_a_mark():
    p = one(scan(["Sugar", "Gelling Agent (INS 441)"], mark="not_visible"))
    assert p["status"] == "contains" and p["more"] == "INS 441 comes from animal collagen (skin and bones)."


def test_green_mark_and_ins_471_is_a_quiet_line_not_a_card():
    # Sushil, 2026-10-11, "Quiet line": the green mark is the maker's declaration (5(4)(a) and (b)).
    j = scan(["Wheat Flour", "Palm Oil", "Emulsifier (471)"], mark="veg")
    assert one(j) is None
    assert quiet(j) == ["INS 471 can be made from plant or animal fat; the label doesn't say which. "
                        "The pack has the green vegetarian mark."]
    assert j["diet"]["results"][0]["state"] == "uncertain"                   # the API keeps the fact


def test_no_mark_and_ins_471_is_amber():
    j = scan(["Wheat Flour", "Palm Oil", "Emulsifier (471)"], mark="not_visible")
    p = one(j)
    assert p["status"] == "uncertain"
    assert p["line"] == "INS 471 can be made from plant or animal fat; the label doesn't say which."
    assert quiet(j) == [diet.NO_MARK["photo"]]


def test_brown_mark_card_with_spices_under_it():
    p = one(scan(["Maida", "Egg Powder (3%)", "Salt", "Spices"], mark="non_veg"))
    assert p["status"] == "contains" and p["line"] == "The pack has the brown non-vegetarian mark."
    [onion] = [d for d in p["diet"] if d["code"] == "no_onion_garlic"]
    assert onion["state"] == "uncertain"


def test_onion_powder_is_red_and_hing_alone_shows_nothing():
    p = one(scan(["Potatoes", "Edible Vegetable Oil", "Onion Powder"]))
    assert p["status"] == "contains" and p["line"] == "Onion is listed: \"Onion Powder\"."
    j = scan(["Whole Wheat Flour", "Edible Vegetable Oil", "Salt", "Asafoetida (Hing)"])
    assert one(j) is None and quiet(j) == [] and "for_you" not in j["screen"]


def test_a_clean_list_with_no_mark_says_so_quietly():
    j = scan(["Fox Nuts (Makhana)", "Rock Salt"], mark="not_visible")
    assert one(j) is None and quiet(j) == [diet.NO_MARK["photo"]]


def test_partial_read_is_one_amber_line():
    p = one(scan(["Rolled Oats", "Salt"], status="partial"))
    assert p["status"] == "cannot_confirm"
    assert p["line"] == diet.cannot_confirm_both(False)


def test_below_095_is_cannot_confirm():
    p = one(scan(["Onion"], conf=0.9))
    assert p["status"] == "cannot_confirm" and p["line"] == diet.cannot_confirm_both(True)


def test_a_household_of_three():
    fam = [{"ref": "me", "age": "adult", "avoid": ["vegetarian", "no_onion_garlic"]},
           {"ref": "p1", "age": "kid", "avoid": ["milk"]},
           {"ref": "p2", "age": "adult", "avoid": ["vegetarian"]}]
    j = scan(["Refined Wheat Flour", "Milk Solids", "Onion Powder", "Gelatine"], profiles=fam)
    assert one(j, "me")["line"] in ("Gelatin is listed: \"Gelatine\".", "Onion is listed: \"Onion Powder\".")
    assert {d["code"]: d["state"] for d in one(j, "me")["diet"]} == {"vegetarian": "contains",
                                                                     "no_onion_garlic": "contains"}
    assert one(j, "p1")["line"] == "Milk is listed: \"Milk Solids\"." and "diet" not in one(j, "p1")
    assert one(j, "p2")["line"] == "Gelatin is listed: \"Gelatine\"."
    assert {d["code"] for d in one(j, "p2")["diet"]} == {"vegetarian"}


def test_profiles_still_carry_only_ref_age_avoid():
    assert screen.parse_profiles([{"ref": "me", "age": "adult", "avoid": ["vegetarian", "no_onion_garlic"]}]) == \
        [{"ref": "me", "age": "adult", "avoid": ["vegetarian", "no_onion_garlic"]}]
    with pytest.raises(screen.ProfileError):
        screen.parse_profiles([{"ref": "me", "age": "adult", "avoid": ["vegetarian"], "diet": "veg"}])
    with pytest.raises(screen.ProfileError):
        screen.parse_profiles([{"ref": "me", "age": "adult", "avoid": ["jain"]}])


def test_the_avoid_field_takes_diet_codes_and_refuses_others():
    r = c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
               data={"replay": json.dumps(answer(["Gelatine"])), "avoid": "vegetarian,milk"})
    assert r.status_code == 200 and r.json()["diet"]["results"][0]["state"] == "contains"
    r = c.post("/scan", files={"back": ("b.png", PNG, "image/png")},
               data={"replay": json.dumps(answer(["Sugar"])), "avoid": "pure_veg"})
    assert r.status_code == 422


def test_get_allergens_lists_the_two_choices():
    assert c.get("/allergens").json()["diets"] == [
        {"code": "vegetarian", "label": "Vegetarian only"}, {"code": "no_onion_garlic", "label": "No onion or garlic"}]


def test_nothing_changes_the_verdict():
    # D-004: the same pack, with and without the diet choices, gets the same verdict.
    ings = ["Wheat Flour", "Gelatine", "Onion Powder", "Emulsifier (471)"]
    a, b = scan(ings, profiles=[]), scan(ings)
    assert a["verdict"] == b["verdict"] and a["display"] == b["display"]


# ------------------------------------------------------------------ Compare

def test_compare_never_picks_a_pack_with_a_diet_line():
    base = {"allergen_statement": None, "confidence": 0.98, "reliable": True}
    packs = [{"id": "a", "name": "Jelly A", "ingredients": ["Sugar", "Gelatine"], "veg_mark": "veg", **base},
             {"id": "b", "name": "Jelly B", "ingredients": ["Sugar", "Water", "Lemon Juice"], "veg_mark": "veg", **base},
             {"id": "c", "name": "Biscuit", "ingredients": ["Wheat Flour", "Emulsifier (471)"], "veg_mark": None, **base}]
    r = c.post("/compare", json={"packs": packs, "age": "young", "avoid": ["vegetarian"], "who": "{name}"}).json()
    assert r["best"] == "b" and r["blocked"] == ["a"] and r["allergen_unsure"] == ["c"]
    [pa] = [p for p in r["packs"] if p["id"] == "a"]
    assert pa["diet"][0]["state"] == "contains" and pa["allergens"] == []


def test_compare_green_mark_ins_471_does_not_block():
    base = {"allergen_statement": None, "confidence": 0.98, "reliable": True}
    packs = [{"id": "a", "name": "Biscuit A", "ingredients": ["Wheat Flour", "Emulsifier (471)"], "veg_mark": "veg", **base},
             {"id": "b", "name": "Biscuit B", "ingredients": ["Wheat Flour", "Sugar"], "veg_mark": "veg", **base}]
    r = c.post("/compare", json={"packs": packs, "age": "young", "avoid": ["vegetarian"]}).json()
    assert not r["blocked"] and not r["allergen_unsure"]
    [pa] = [p for p in r["packs"] if p["id"] == "a"]
    assert pa["diet"][0].get("quiet") is True

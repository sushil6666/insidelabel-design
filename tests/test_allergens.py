"""Tests for allergens.py. All labels are invented, not real products."""

from insidelabel.lenses.allergens import ALLERGENS, check, AllergenResult

LIST = ["Refined wheat flour (Maida)", "Sugar", "Cocoa butter", "Emulsifier (INS 322)",
        "Coconut milk powder", "Cashew nuts (3%)", "Salt"]


def test_contains_from_ingredients():
    r = check(LIST, None, ["gluten", "tree_nuts"])
    assert r["gluten"].state == "contains"          # maida
    assert r["tree_nuts"].state == "contains"       # cashew


def test_excluded_phrases_are_not_milk():
    # cocoa butter and coconut milk are not dairy
    r = check(LIST, None, ["milk"])
    assert r["milk"].state == "not_listed"


def test_unsourced_lecithin_is_uncertain_for_soy():
    r = check(LIST, None, ["soy"])
    assert r["soy"].state == "uncertain"
    r2 = check(["Wheat flour", "Emulsifier (Sunflower Lecithin)"], None, ["soy"])
    assert r2["soy"].state == "not_listed"
    r3 = check(["Wheat flour", "Emulsifier (Soya Lecithin)"], None, ["soy"])
    assert r3["soy"].state == "contains"


def test_specific_nut_is_not_ambiguous_for_peanut():
    r = check(LIST, None, ["peanut"])
    assert r["peanut"].state == "not_listed"        # "cashew nuts" names the nut
    r2 = check(["Sugar", "Mixed nuts (5%)"], None, ["peanut", "tree_nuts"])
    assert r2["peanut"].state == "uncertain" and r2["tree_nuts"].state == "uncertain"


def test_statement_split_on_one_sentence():
    st = "Contains wheat and milk, may contain traces of peanuts"
    r = check(["Sugar"], st, ["gluten", "milk", "peanut"])
    assert r["gluten"].state == "contains"
    assert r["milk"].state == "contains"
    assert r["peanut"].state == "may_contain"


def test_facility_wording_counts_as_may_contain():
    st = "Manufactured in a facility that also processes sesame."
    assert check(["Rice flour"], st, ["sesame"])["sesame"].state == "may_contain"


def test_gluten_free_statement_is_not_contains():
    assert check(["Rice flour", "Sugar"], "Gluten free.", ["gluten"])["gluten"].state == "not_listed"


def test_low_confidence_never_interprets():
    r = check(LIST, None, ["milk"], confidence=0.9)
    assert r["milk"].state == "cannot_confirm"
    assert check(LIST, None, ["milk"], reliable=False)["milk"].state == "cannot_confirm"


def test_sulphite_by_ins_number():
    assert check(["Raisins", "Preservative (223)"], None, ["sulphite"])["sulphite"].state == "contains"


def test_parent_text_never_says_free_or_safe():
    for code in ALLERGENS:
        for state in ("contains", "may_contain", "uncertain", "not_listed", "cannot_confirm"):
            from insidelabel.lenses.allergens import AllergenResult
            for seen in (True, False):
                t = AllergenResult(code, state, "x", seen).parent_text("Riya").lower()
                assert " free" not in t and "safe" not in t, t


def test_missing_statement_is_mentioned():
    r = check(["Rice flour", "Sugar"], None, ["milk"])
    assert "didn't see" in r["milk"].parent_text()

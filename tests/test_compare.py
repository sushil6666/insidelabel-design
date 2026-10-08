"""Tests for compare.py. All labels are invented, not real products."""

from insidelabel.lenses.compare import Product, compare, render

CREAM = Product("a", "Orange Cream Biscuit", [
    "Refined wheat flour (Maida)", "Sugar", "Edible vegetable oil (Palm)", "Invert syrup",
    "Colour (INS 110)", "Emulsifiers (322, 471)", "Raising agent (500(ii))", "Iodised salt",
    "Artificial flavouring substances (orange)",
])
DIET = Product("b", "Sugar-Free Marie", [
    "Refined wheat flour (Maida)", "Maltodextrin", "Edible vegetable oil (Palm)",
    "Sweetener (INS 955)", "Emulsifier (322)", "Raising agent (500(ii))", "Salt",
])
ATTA = Product("c", "Whole Wheat Jeera Biscuit", [
    "Whole wheat flour (Atta) 62%", "Edible vegetable oil (Palm)", "Sugar", "Cumin (Jeera) 2%",
    "Raising agent (500(ii))", "Iodised salt",
])
MYSTERY = Product("d", "Choco Filled Cookie", [
    "Refined wheat flour", "Sugar", "Cocoa solids", "Emulsifier (1201)", "Salt",
])


def test_best_pick_and_reasons():
    r = compare([CREAM, DIET, ATTA], age="kid")
    assert r["best"].id == "c"
    assert "No artificial colours" in r["why_best"]
    assert "No artificial sweeteners" in r["why_best"]
    assert "Made mainly from whole wheat" in r["why_best"]


def test_unknown_additive_is_never_best():
    # MYSTERY has no colours or sweetener, but INS 1201 isn't in the database.
    r = compare([CREAM, MYSTERY], age="kid")
    assert r["best"].id == "a"
    assert MYSTERY in r["not_checked"]
    assert "1201" in MYSTERY.unknown_ins


def test_unreliable_scan_not_ranked():
    blurry = Product("e", "Blurry Pack", ATTA.ingredients, reliable=False)
    r = compare([CREAM, blurry], age="kid")
    assert blurry in r["not_checked"]


def test_nothing_checkable():
    blurry = Product("e", "Blurry Pack", ATTA.ingredients, reliable=False)
    r = compare([MYSTERY, blurry], age="kid")
    assert r["best"] is None and not r["tie"]


def test_tie_is_honest():
    twin = Product("f", "Whole Wheat Ajwain Biscuit",
                   [i.replace("Cumin (Jeera)", "Ajwain") for i in ATTA.ingredients])
    r = compare([ATTA, twin], age="kid")
    assert r["best"] is None and len(r["tie"]) == 2


def test_sweetener_is_fact_only():
    # v1.1: no legal claim about sweetener warnings (FSSAI FAQ, June 2022).
    compare([DIET, ATTA], age="kid")
    texts = [f.parent_text for f in DIET.facts if f.key.startswith("sweetener:")]
    assert texts == ["Has an artificial sweetener (Sucralose)."]
    assert all("rule" not in t.lower() and "fssai" not in t.lower() for t in texts)


MILKY = Product("g", "Milk Rusk", [
    "Wheat flour (Atta)", "Sugar", "Milk solids (4%)", "Edible vegetable oil (Palm)", "Yeast",
], allergen_statement="Contains wheat and milk.")
TRACES = Product("h", "Plain Jeera Crackers", [
    "Whole wheat flour", "Edible vegetable oil (Palm)", "Cumin", "Salt",
], allergen_statement="Contains wheat. May contain traces of milk and nuts.")


def test_allergen_blocks_best_pick():
    # MILKY would otherwise compete; it contains milk, so it can't be the pick.
    r = compare([MILKY, CREAM], age="kid", avoid=["milk"], who="Riya")
    assert MILKY in r["blocked"]
    assert r["best"].id == "a"
    # D-188: a "not listed" line isn't shown; the pick says it passed the avoid list.
    assert r["allergen_lines"] == []
    assert "RIYA" in render(r)


def test_may_contain_is_a_no_by_default():
    r = compare([TRACES, ATTA], age="kid", avoid=["milk"])
    assert TRACES in r["blocked"]
    r2 = compare([TRACES, ATTA], age="kid", avoid=["milk"], strict_may_contain=False)
    assert TRACES in r2["allergen_unsure"]


def test_all_blocked_says_so():
    r = compare([MILKY, TRACES], age="kid", avoid=["milk"])
    assert r["best"] is None
    assert "NONE OF THESE PACKS" in render(r)


def test_no_numbers_in_parent_text():
    compare([CREAM, DIET, ATTA], age="toddler")
    for p in (CREAM, DIET, ATTA):
        for f in p.facts:
            assert "INS" not in f.parent_text  # technical detail stays behind the tap


if __name__ == "__main__":
    print(render(compare([CREAM, DIET, ATTA, MYSTERY], age="kid")))
    print("\n" + "-" * 60 + "\n")
    print(render(compare([MILKY, TRACES, ATTA], age="kid", avoid=["milk"], who="Riya")))

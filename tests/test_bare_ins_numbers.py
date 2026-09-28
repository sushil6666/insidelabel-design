"""
Regression test from a real label: Limca 2L PET (Hindustan Coca-Cola),
FSSAI Lic. 10012022000261.

THE DEFECT (fixed)
    Indian labels routinely print additives as bare numbers inside a class
    bracket -- "ACIDITY REGULATORS (330, 331(iii))" -- with no INS or E prefix.
    tokenize() discarded every all-numeric token as noise before extract_ins()
    could look at it, so extract_ins()'s bare-3-digit branch was unreachable.
    Five additives on this label were invisible, two of them already in
    additives.json, and the grade read A instead of B.

THE FIX
    prefix_bare_ins() rewrites bare numbers as explicit INS numbers, but only
    inside a bracket introduced by an additive class word. Context, not shape.

WHY NOT JUST EXEMPT 3-DIGIT TOKENS FROM THE NOISE FILTER
    200 is sorbic acid, 250 is sodium nitrite, 500 is sodium bicarbonate --
    all in additives.json, and all everyday quantities on a pack. A shape-based
    rule reads "200 ml" as a preservative and "250 kcal" as a curing agent.
    The class word is the only thing separating the two cases, which is why
    test_quantities_are_not_additives below is the important test in this file,
    not the Limca one.

Run:  python3 tests/test_bare_ins_numbers.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from insidelabel.core import engine

LIMCA = ("CARBONATED WATER, SUGAR, ACIDITY REGULATORS (330, 331(iii)), "
         "STABILIZERS (414,471), PRESERVATIVE (211), FLAVOURS (NATURAL, "
         "NATURE-IDENTICAL & ARTIFICIAL (LEMON) FLAVOURING SUBSTANCES)")


def test_bare_numbers_in_class_brackets_are_read():
    result = engine.analyze(LIMCA)
    matched = " ".join(f["matched_as"] for f in result["flags"])
    assert "INS 211" in matched, "sodium benzoate missed"
    assert "INS 471" in matched, "mono- and diglycerides missed"
    assert "INS 330" in matched, "citric acid missed"


def test_limca_grades_b_not_a():
    result = engine.analyze(LIMCA)
    # 76 before class-only lows scored 0 (2026-09-25); 80 until D-121 let the
    # tokenizer find "stabilizers" (NOVA marker, low) outside its brackets.
    assert result["score"] == 76, result["score"]
    assert result["grade"] == "B", result["grade"]


def test_quantities_are_not_additives():
    """The one that matters. No class word means no rewrite."""
    panel = ("SERVING = 200ml : 10 SERVINGS IN THIS PACK. ENERGY 250 kcal, "
             "SODIUM 5.6 mg PER 100ml. BASED ON A 2000 kcal DIET.")
    assert engine.analyze(panel)["flags"] == []
    for text in ("Net quantity 200 ml", "Net weight 500 g", "Energy 250 kcal"):
        assert engine.prefix_bare_ins(text) == text, text


def test_rewrite_is_idempotent():
    once = engine.prefix_bare_ins(LIMCA)
    assert engine.prefix_bare_ins(once) == once
    assert engine.prefix_bare_ins("Emulsifiers (INS 322, INS 471)") == \
        "Emulsifiers (INS 322, INS 471)"


def test_partially_prefixed_bracket_is_completed():
    assert engine.prefix_bare_ins("Emulsifiers (INS 322, 471)") == \
        "Emulsifiers (INS 322, INS 471)"


def test_non_additive_brackets_untouched():
    for text in ("Cocoa Solids (12%)", "Refined Wheat Flour (Maida)",
                 "Colour (Caramel)", "Milk Solids (20%)"):
        assert engine.prefix_bare_ins(text) == text, text


def test_nested_roman_numerals_survive():
    assert engine.prefix_bare_ins("Raising Agents (500(ii), 503(ii))") == \
        "Raising Agents (INS 500(ii), INS 503(ii))"


def test_existing_labels_unchanged():
    """Prefixed labels must score exactly as they did before the fix."""
    for text, score in [
        ("Peanuts, Salt", 100),
        ("Refined wheat flour (maida), Sugar, Edible vegetable oil (palm), "
         "Invert syrup, Milk solids, Cocoa solids, Emulsifiers (INS 322, INS 471), "
         "Raising agents (INS 500(ii), INS 503(ii)), Salt, "
         "Added flavours (natural and artificial), INS 621", 56),  # 60 until D-121: "emulsifiers" now found (NOVA, low)
    ]:
        assert engine.analyze(text)["score"] == score


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("\nAll pass. The defect is fixed and quantities are still safe.")

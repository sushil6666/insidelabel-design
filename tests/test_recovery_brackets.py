"""
D-164: D-093's recovery takes an omitted additive's whole printed entry, closed by
bracket matching (core/tokenize), so the engine can read every number in it.

Before, a regex stopping at the first ")" cut "Raising agents (500(ii), 503(ii))" to
"Raising agents (500(ii)" and left 503 as a bare "(503)": 500 and 503 were missing
from the result while its caveat said "Recovered and included in the verdict"
(found under D-160).
"""
import pytest

from insidelabel.core.tokenize import ins_numbers
from insidelabel.extraction.providers import ocr_check

LISTED = ["Sugar", "Salt"]


def recover(printed, missing):
    text = f"Ingredients: Sugar, {printed}, Salt."
    result = {"available": True, "missing": missing, "ocr_text": text}
    fixed, recovered = ocr_check.recover_from(result, LISTED)
    assert fixed == LISTED + recovered
    return recovered


@pytest.mark.parametrize("printed, missing, entry", [
    ("Raising agents (500(ii), 503(ii))", ["500", "503"], "Raising agents (500(ii), 503(ii))"),
    ("Preservative (211)", ["211"], "Preservative (211)"),
    ("Acidity regulator (INS 330)", ["330"], "Acidity regulator (330)"),
    ("Humectant [420(ii)]", ["420"], "Humectant [420(ii)]"),
    ("Mix {Emulsifiers [481(i) & 471]}", ["471", "481"], "Emulsifiers [481(i) & 471]"),
    ("Colour (150d)", ["150d"], "Colour (150d)"),
])
def test_the_whole_entry_comes_back_once_and_reads(printed, missing, entry):
    recovered = recover(printed, missing)
    assert recovered == [entry]                     # two numbers of one group: one entry
    assert set(missing) <= ins_numbers(recovered)   # the engine reads every number


def test_a_compound_ingredient_gives_only_the_bracket_holding_the_number():
    # The model kept the compound; recovering it whole would list it twice.
    assert recover("Compound chocolate (sugar, cocoa, emulsifier (322))", ["322"]) == ["emulsifier (322)"]


def test_a_number_with_no_name_before_it_keeps_the_bare_fallback():
    assert recover("(319)", ["319"]) == ["(319)"]

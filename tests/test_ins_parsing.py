"""INS number parsing edge cases. One pattern (tokenize.INS_RE) serves the engine and the OCR cross-check."""
import pytest

from insidelabel.core import engine, tokenize as tk
from insidelabel.extraction.providers import ocr_check


def ins_of(text):
    return [i for i in (tk.extract_ins(t) for t in engine.tokenize(text)) if i]


@pytest.mark.parametrize("text, expected", [
    # 4-digit INS numbers (modified starches, enzymes, humectants)
    ("Modified Starches (1422, 1412, 1440, 1442)", ["1422", "1412", "1440", "1442"]),
    ("Stabiliser (INS 1450)", ["1450"]),
    ("Humectants (420, 422, 1520)", ["420", "422", "1520"]),
    # suffixes still work
    ("Colours (150c, 150d)", ["150c", "150d"]),
    ("Emulsifier (INS 472e)", ["472e"]),
    ("Sweetener (INS 960a)", ["960a"]),
    ("Emulsifier (E471)", ["471"]),
    ("Acidity regulators (330, 331(iii))", ["330", "331"]),
    # quantities are never additives
    ("Tomato paste 250 g", []),
    ("Tomato paste 250g", []),
    ("Raisins 150g", []),
    ("Spice mixture 330 mg", []),
    ("Fruit juice 100%", []),
    ("Energy 250 kcal", []),
])
def test_extraction(text, expected):
    assert ins_of(text) == expected


def test_quantity_after_word_ending_in_e_is_not_flagged():
    r = engine.analyze("Tomato paste 250 g, Sugar, Salt")
    assert not any("250" in f["matched_as"] for f in r["flags"])


def test_four_digit_is_not_truncated_to_three():
    # 1422 must never be read as 142 (Green S), 1450 never as 145.
    assert "142" not in ins_of("Modified starch (INS 1422)")
    assert "145" not in ins_of("Stabiliser (INS 1450)")


def test_ocr_cross_check_uses_the_same_pattern():
    assert ocr_check._INS is tk.INS_RE
    assert ocr_check._ins_numbers("Thickener (1442), Tomato paste 250 g") == {"1442"}


def test_engine_has_no_private_copy():
    assert engine.prefix_bare_ins is tk.prefix_bare_ins
    assert not hasattr(engine, "_BARE_NUM")


@pytest.mark.parametrize("text, expected", [
    ("HUMECTANT [420(ii)]", ["420"]),
    ("PRESERVATIVES (282 & 202)", ["282", "202"]),
    ("BAKERY IMPROVER MIX {EMULSIFIERS [481(i) & 471], ANTICAKING AGENT [170(i)], "
     "FLOUR TREATMENT AGENTS [1100(i) & 1101(i)] & ANTIOXIDANT (300)}",
     ["481", "471", "170", "1100", "1101", "300"]),
    ("Enzyme (1100(iii), 1104)", ["1100", "1104"]),
])
def test_real_label_shapes(text, expected):
    assert sorted(ins_of(text)) == sorted(expected)


def test_fdc_ampersand_is_not_split():
    assert "fd&c yellow 5" in engine.tokenize("Colour (FD&C Yellow 5)")


def test_every_printed_ins_on_gold_labels_is_read():
    """Guards the parser itself. eval_vision.py cannot: gold and prediction share it."""
    import glob, json, os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in glob.glob(os.path.join(root, "gold", "*.json")):
        with open(f, encoding="utf-8") as fh:
            raw = ", ".join(json.load(fh)["ingredients"])
        printed = set(re.findall(r"(?<![\d.])(\d{3,4})(?:\s*[a-f])?(?![\d.%])", raw))
        got = {i.rstrip("abcdef") for i in ins_of(raw)}
        assert printed == got, f"{os.path.basename(f)}: missed {printed - got}, extra {got - printed}"


@pytest.mark.parametrize("text, expected", [
    ("COLOURS (160 a(ii), 129)", ["160a", "129"]),
    ("Raising agent (503 i)", ["503"]),
    # "and" is not a separator (it would split "mono- and diglycerides"); this
    # only guards that "a" of "and" is never read as a suffix.
    ("Emulsifier (322 and 471)", ["322"]),
])
def test_spaced_suffix(text, expected):
    assert sorted(ins_of(text)) == sorted(expected)


def test_no_unknown_ins_on_gold_labels():
    """Every INS number on a gold label has a row in additives.json."""
    import glob, json, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in glob.glob(os.path.join(root, "gold", "*.json")):
        with open(f, encoding="utf-8") as fh:
            raw = ", ".join(json.load(fh)["ingredients"])
        unknown = [i for i in ins_of(raw) if i not in engine._ADDITIVE_BY_INS]
        assert not unknown, f"{os.path.basename(f)}: no additives.json row for {unknown}"

"""
Brackets of every kind, at any depth, are groups: nothing splits inside one.

The tokenizer split at every comma, whatever the bracket depth, and knew only
one level of ( ) and [ ]. So "Spices (Chilli, Turmeric)" gave "spices (chilli"
and "turmeric)", and the first supermarket run (2026-09-27) showed
"emulsifier ]", "antioxidant }" and "ins 472(e" from Bisk Farm TOP GOLD and
Sundrop POPZ. D-115 shows a marker in the label's words, so a user could read
"such as emulsifier ]". D-121: separators split only outside brackets, each
group is tokenized in turn, and an INS sub-form "(ii)" stays on its number.
Labels are copied from STATE.md's notes or the gold set, or invented.
"""
import glob
import json
import os

from insidelabel.core import engine
from insidelabel.core.tokenize import ins_numbers, tokenize

BRACKETS = set("()[]{}")
GOLD = os.path.join(os.path.dirname(__file__), "..", "gold")


def test_a_comma_inside_brackets_does_not_split_the_entry():
    assert tokenize("Spices (Chilli, Turmeric), Salt") == ["spices", "chilli", "turmeric", "salt"]


def test_nested_square_brackets():
    assert tokenize("EMULSIFIERS [450(i), 472(e)], Salt") == [
        "emulsifiers", "ins 450(i)", "ins 472(e)", "salt"]
    assert tokenize("PLAIN CHOCOLATE CHIPS (6.2%) [SUGAR, EMULSIFIER [LECITHIN (FROM SOYBEAN)], "
                    "NATURAL FLAVOURS AND NATURAL FLAVOURING SUBSTANCES], SALT") == [
        "plain chocolate chips", "sugar", "emulsifier", "lecithin", "from soybean",
        "natural flavours and natural flavouring substances", "salt"]


def test_braces_are_brackets():
    assert tokenize("Multigrain flour mix {rice meal, oat meal}, Antioxidant {TBHQ}") == [
        "multigrain flour mix", "rice meal", "oat meal", "antioxidant", "tbhq"]
    assert tokenize("Mix {Emulsifiers [481(i) & 471], Antioxidant (319)}") == [
        "mix", "emulsifiers", "ins 481(i)", "ins 471", "antioxidant", "ins 319"]


def test_a_sub_form_stays_on_its_number():
    assert tokenize("Colour (160 a(ii)), Raising agent (500 (ii))") == [
        "colour", "ins 160 a(ii)", "raising agent", "ins 500 (ii)"]
    assert ins_numbers("Raising Agents (500(ii), 503(ii))") == {"500", "503"}


def test_a_split_compound_leaves_no_bracket_behind():
    """The reader sometimes ends an entry inside a compound; each half still reads cleanly."""
    assert tokenize("Multigrain flour mix {rice meal") == ["multigrain flour mix", "rice meal"]
    assert tokenize("oat meal }") == ["oat meal"]
    assert tokenize("Multigrain flour mix {rice meal, oat meal }, Salt") == [
        "multigrain flour mix", "rice meal", "oat meal", "salt"]


def test_mismatched_brackets_still_close():
    """An OCR "(322]" is still a group, so its bare number is still read."""
    assert tokenize("Emulsifier (322], Salt") == ["emulsifier", "ins 322", "salt"]
    assert ins_numbers("Antioxidant [319), Salt") == {"319"}


def test_no_gold_label_gives_a_token_with_a_bracket_fragment():
    """A token may keep a whole sub-form "(ii)"; it never keeps half a bracket."""
    paths = sorted(glob.glob(os.path.join(GOLD, "*.json")))
    assert paths
    for path in paths:
        ingredients = json.load(open(path, encoding="utf-8"))["ingredients"]
        for t in tokenize(", ".join(ingredients)):
            stripped = t.replace("(", "").replace(")", "")
            assert not BRACKETS & set(stripped), (path, t)
            assert t.count("(") == t.count(")"), (path, t)


def test_a_class_word_before_its_brackets_is_found():
    """D-121: "STABILIZERS (414,471)" was one token, "stabilizers (ins 414", so the
    NOVA stabiliser marker in data/nova_markers.json never matched it."""
    r = engine.analyze("Carbonated water, Sugar, Stabilizers (414, 471)")
    assert "NOVA marker: Stabiliser / thickener / humectant (cosmetic use)" in [
        f["matched_as"] for f in r["flags"]]

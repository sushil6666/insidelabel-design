"""
INS 319 (TBHQ), 472e (DATEM) and 296 (malic acid) have rows (2026-09-28).

The first supermarket run (2026-09-27) found TBHQ on Sundrop POPZ ("Antioxidant
(TBHQ)") and Bisk Farm TOP GOLD ("ANTIOXIDANT (319)"), and 472(e) on Bisk Farm
and Anmol dream LITE: all passed with no card. The basis of each row was read
from the FSSAI compendium XXVI, Appendix A (D-046): 296 is in the GMP table
(p. 739, "Malic acid, DL-"); 319 and 472e appear only in the category tables,
with numeric limits. Names and classes from the compendium's INS list.
"""
from insidelabel.core import engine
from insidelabel.core.tokenize import ins_numbers


def _matched(text):
    return [f["matched_as"] for f in engine.analyze(text)["flags"] if f["type"] == "additive"]


def test_tbhq_by_number_and_by_name():
    assert _matched("Palmolein, ANTIOXIDANT (319)") == ["INS 319 (Tertiary butylhydroquinone (TBHQ))"]
    assert _matched("Rice meal, Antioxidant (TBHQ)") == ["Tertiary butylhydroquinone (TBHQ) (INS 319)"]


def test_472e_however_the_letter_is_printed():
    for text in ("EMULSIFIERS [450(i), 472(e)]", "Emulsifier (INS 472e)", "Emulsifier (472 (e))",
                 "Emulsifier (E472e)"):
        assert "472e" in ins_numbers(text), text
        assert any(m.startswith("INS 472e ") for m in _matched(text)), text


def test_a_roman_sub_form_is_not_a_letter():
    assert ins_numbers("Emulsifier (322(i)), Raising agent (500 (ii))") == {"322", "500"}


def test_malic_acid():
    assert _matched("Acidity regulator (296)") == ["INS 296 (Malic acid)"]
    assert _matched("Malic acid") == ["Malic acid (INS 296)"]


def test_the_three_rows_do_not_move_a_score_on_their_own():
    """Class-only 'low' (319, 472e) and 'none' (296) score 0 (additives.json _meta.scoring)."""
    assert engine.analyze("Wheat flour, Antioxidant (TBHQ), Acidity regulator (296)")["score"] == 100

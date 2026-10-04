"""
D-157 (refines D-118): Cloud Vision's text of the back confirms Gemini's list
even with a date stamp printed across the panel, or words cut where the parts
of a back overlap. Problem report #5 (Sushil, 2026-10-04) is the case: a Nestle
Choco Coated Wafer (8901058009439), refused twice with "One clearer photo,
please." although Gemini read the list right both times. The texts below are
Cloud Vision's, as stored on the two scans (first 600 characters).

Strict otherwise: a whole ingredient word Gemini doesn't have still refuses,
and a cut word that starts no word of the list still counts.

D-158 (the advisor's review, 2026-10-04): a word counts as cut only at the start
or end of a line, and an allergen word or a one-word ingredient name never does,
so "Nutmeg, Nut," or "Eggless mix, ... Egg" is a dropped ingredient again.
"""
from insidelabel.review import checker

GEMINI = ["Sugar", "Refined Wheat flour (Maida)", "Hydrogenated vegetable fats", "Fractionated vegetable fat",
          "Milk solids", "Cocoa solids (3.3%)", "Emulsifiers (Soya lecithin and 476)", "Raising agent (500(ii))",
          "Yeast", "Iodized salt", "Flour treatment agent (516) and Artificial (Vanilla) flavouring substances."]


def lines(text):
    return text.replace(" | ", "\n")


# Scan 8bd1c116: the back in 3 parts; Cloud Vision read the overlaps twice.
PARTS = lines(
    "Choco Coated Wafer | INGREDIENTS: | AUGT | Sugar, Refined Wheat flour (Maida), Hydrogenated vegetable fats, "
    "Fractionated | vegetable fat, Milk solids, Cocoa solids (3.3%), Emulsifiers (Soya lecithin | and 476), "
    "Raising agent (500/)). Yeast, lodized salt Flour treatment | agent (516) | water | Choce DIENT'S | ING | "
    "vegetable fat, Milks | solids, Cocoa solids (3.3%), Emulsifiers (Soya leci | Sugar, Refined Wheat flour "
    "(Maida), Hydrogenated vegetable fats, Frac | and 476), Raising agent (500()), Yeast, lodized salt, Flour "
    "treatment | (516) and Artificial (Vanilla) flavouring substances. | Allergen Note: Contains Wheat, Soy, S")

# Scan 8c46004c: one photo, the stamp "AUG/26-APR" across the panel.
STAMPED = lines(
    "Choco Coated Wafer | INGREDIENTS: | AUG/26-APR | Sugar, Refined Wheat flour (Maida), Hydrogenated vegetable "
    "fats, Fractionated | vegetable fat, Milk solids, Cocoa solids (3.3%), Emulsifiers (Soya lecithin | and 476), "
    "Raising agent (500) Yeast lodized salt-Flour treatment | agent (516) and Artificial (Vanilla) flavouring "
    "substances. | Allergen Note: Contains Wheat, Soy Sesame and Milk | AUN | Trans Fa | Sodium | Nutrition "
    "Information* | Energy (kcal) | Protein (a) | Carbohydrateg | Total Sugars (g) | Added Sugars (9) | Fat g | "
    "Approxim | bar (10.4 g) | Per 100g | 452 | Nestle | 5.7 | KNOW Y | 52.8 | 1 serve= | 37.4 Pack cont | "
    "33.8 | Per serve co | 24.2")


def test_the_stamped_single_photo_is_now_confirmed():
    assert checker.independent_read(GEMINI, STAMPED) == (True, [], [])        # was LOST ['apr', 'aug']
    assert checker.independent_read_confirmed(GEMINI, STAMPED)


def test_the_three_part_back_loses_only_its_stray_words():
    # Was ['augt', 'choce', 'dient', 'frac', 'ing', 'leci', 'water']. "augt" is the stamp
    # misread, alone on its line; "frac", "leci" start words of the list; "ing", "dient"
    # are the heading read twice. "choce" (a cut, misread "Choco") starts no word of the
    # list, and "water" is a whole word: both still count (D-157's open question).
    assert checker.independent_read(GEMINI, PARTS) == (True, [], ["choce", "water"])


def test_stamp_words_and_months_with_digits():
    text = lines("INGREDIENTS: | MFD 12/AUG/25 EXP: 11 FEB 26 BATCH NO. L123 | Sugar, Salt.")
    assert checker.independent_read(["Sugar", "Salt"], text) == (True, [], [])


def test_a_dropped_real_ingredient_still_refuses():
    no_salt = [x for x in GEMINI if x != "Iodized salt"]
    found, missing, lost = checker.independent_read(no_salt, STAMPED)
    assert found and "salt" in lost
    assert not checker.independent_read_confirmed(no_salt, STAMPED)


def test_aug_inside_a_real_word_is_untouched():
    text = lines("INGREDIENTS: Sugar, Sausage, Salt. AUG/26")
    assert checker.independent_read(["Sugar", "Salt"], text)[2] == ["sausage"]


def test_a_word_like_a_month_in_running_text_still_counts():
    # "mayo" is one letter from "may", but it isn't in a stamp: no digit or "/" next to
    # it, and not alone on its line.
    text = lines("INGREDIENTS: Sugar, Eggless mayo, Salt.")
    assert checker.independent_read(["Sugar", "Eggless", "Salt"], text)[2] == ["mayo"]


def test_a_cut_word_that_starts_nothing_in_the_list_still_counts():
    text = lines("INGREDIENTS: Sugar, Palm fat, Frac | Salt.")
    assert checker.independent_read(["Sugar", "Palm fat", "Salt"], text)[2] == ["frac"]


# ---------------------------------------------------------------- D-158: cut words, narrowed

def lost(ingredients, text):
    return checker.independent_read(ingredients, lines(text))[2]


def test_a_dropped_word_beside_a_longer_one_mid_line_refuses():
    # Measured on main 14c2fc6, where all three passed as cut words.
    assert lost(["Sugar", "Nutmeg", "Salt"], "Ingredients: Sugar, Nutmeg, Nut, Salt") == ["nut"]
    assert lost(["Wheat flour", "Eggless mix", "Salt"], "Ingredients: Wheat flour, Eggless mix, Egg, Salt") == ["egg"]
    assert lost(["Cornflour", "Salt"], "Ingredients: Cornflour, Corn, Salt") == ["corn"]


def test_an_allergen_at_a_line_end_is_never_a_cut_word():
    # Guard 2: where a cut could happen, an allergen word (allergens.json) still refuses.
    assert lost(["Sugar", "Nutmeg", "Salt"], "Ingredients: Sugar, Nutmeg, Salt, Nut | Net weight") == ["nut"]
    assert lost(["Wheat flour", "Eggless mix", "Salt"],
                "Ingredients: Wheat flour, Eggless mix, Salt, Egg | Net weight") == ["egg"]


def test_a_plain_word_at_a_line_end_beside_a_longer_one_is_still_taken_as_cut():
    # What D-158 leaves: "corn" is neither an allergen word nor a synonym, so at a line's
    # end beside "Cornflour" it reads as a cut. Recorded in D-158 as an open question.
    assert lost(["Cornflour", "Salt"], "Ingredients: Cornflour, Salt, Corn | Net weight") == []


def test_report_5_keeps_its_d157_result():
    assert checker.independent_read(GEMINI, STAMPED) == (True, [], [])
    assert checker.independent_read(GEMINI, PARTS) == (True, [], ["choce", "water"])

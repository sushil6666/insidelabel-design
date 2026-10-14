"""
D-201 (Sushil, 2026-10-13, accepted with five changes): an infant result a parent can use.

With INSIDELABEL_INFANT_TO_USERS on, an infant result reads: the allergen cards, the kind once,
"Worth knowing" (an added sugar where the list names one, each nutrient outside FSSAI's range,
with a neutral range bar), "Good to know" (the count inside FSSAI's ranges with "See all",
additives, one notices line with "Photograph the side"), and a Compare button for its kind.
Switch off stays D-140's shadow byte for byte (tests/test_infant_to_users.py).

Here: the Amulspray pack end to end; a pack with nothing outside its range; no added sugar; a
min-only row; the side photo finding 2 of 4, then all 4, and a photo it can't read; infant
Compare with no winner words; the child card on an infant pack; the brand shown once; and the
hard lines (no adult daily intake, nothing beside mother's milk, D-201's five words).
"""
import json
import os
import re
import shutil
import subprocess

import pytest
from test_infant_to_users import (BOILED, NOTICE, STATEMENTS, WINNER_WORDS, _blocks, _packs, _without_the_notice,
                                  c, compare, infant, scan)
from test_pack_kind import reading, st
from test_wording import assert_clean, infant_hits, strings

from insidelabel.api import main
from insidelabel.extraction.providers import cloud_vision
from insidelabel.lenses import infant as infant_lens
from insidelabel.lenses import screen, side_by_side

HERE = os.path.dirname(os.path.abspath(__file__))
AMUL = json.load(open(os.path.join(HERE, "fixtures", "amulspray_8901262080033.json"), encoding="utf-8"))
BABY = [{"ref": "me", "age": "adult", "avoid": []}, {"ref": "p1", "age": "baby", "avoid": []}]
ADULT_INTAKE = re.compile(r"%\s*(of\s+)?(your\s+)?daily|\bRDA\b|daily intake|daily value|\bper day\b", re.I)


def amulspray(key="amul", profiles=BABY):
    v = reading(AMUL["ingredients"], [st(t, face) for t, face in AMUL["statements"]],
                allergen=AMUL["allergen_statement"], name=AMUL["name"])
    v["product"]["brand"] = AMUL["brand"]
    v["front_identity"] = dict(AMUL["front_identity"])
    v["nutrition"] = json.loads(json.dumps(AMUL["nutrition"]))
    return scan(v, key=key, ocr=AMUL["ocr_text"], profiles=profiles)


def with_table(v, rows, basis="per 100 g"):
    v["nutrition"] = {"status": "read", "per_100_basis": basis,
                      "rows": [{"nutrient": n, "per_100": a, "unit": None} for n, a in rows]}
    return v


def table_text(rows):
    return " ".join(f"{n} {a}" for n, a in rows)


def _texts(obj):
    return " ".join(strings(obj))


# ---------------------------------------------------------------- Amulspray, end to end

def test_amulspray_end_to_end(infant_on):
    j = amulspray()
    s = j["screen"]
    assert list(j)[0] == "allergens" and j["verdict"] is None and j["pack_kind"]["code"] == "infant"
    assert j.get("score") is None and j["nutrition"] is None
    # The kind once: the printed name in the headline, the rules in one line, why a tap away (7(3)).
    assert s["headline"]["text"] == 'This pack says "INFANT MILK FOOD".'
    assert s["kind"]["lines"] == ["We check it against FSSAI's rules for infant formula."]
    assert s["kind"]["evidence"] == [] and s["sections"] == []
    assert s["kind"]["why"]["title"] == "Why infant formula"
    assert s["kind"]["why"]["text"] == ("FSSAI's rules make \"Infant Milk Food\" a name for one kind of infant formula "
                                        "(regulation 7(3), PDF p. 12), so we use the infant formula table.")
    # Worth knowing: the added sugar, then Protein, the one nutrient outside FSSAI's range.
    worth = s["infant"]["worth"]
    assert worth["title"] == "Worth knowing" and [x["id"] for x in worth["items"]] == ["sugar", "protein"]
    assert worth["items"][0]["text"] == ("Sugar is the 2nd of 4 ingredients. Added sugars: 18 g per 100 g; "
                                         "total sugars: 50 g, as printed.")
    protein = worth["items"][1]
    assert protein["text"] == "Protein: 22 g per 100 g. FSSAI's range: 10 to 16 g."
    assert {k: protein["bar"][k] for k in ("value", "low", "high", "value_text", "low_text", "high_text")} == {
        "value": 22.0, "low": 10.0, "high": 16.0, "value_text": "22 g", "low_text": "10", "high_text": "16 g"}
    lo, hi = protein["bar"]["scale"]
    assert lo < 10.0 and hi > 22.0                                # the range and the pack's number both fit
    assert protein["more"]["title"] == "From FSSAI's rules"
    assert protein["more"]["lines"] == ["Per 100 kcal: 4.89 g. FSSAI's range: 2.10 to 3.40 g.",
                                        "FSSAI's rules for infant foods apply to packs made from 1 October 2022."]
    assert protein["more"]["sources"][0]["page"] == "7(1)(g) item 2, PDF p. 8"
    # Good to know: the count with See all, additives, notices.
    good = _blocks(s)
    assert s["infant"]["good"]["title"] == "Good to know" and list(good) == ["nutrients", "additives", "notices"]
    n = good["nutrients"]
    assert n["lines"] == ["26 of 27 nutrients we compared are inside FSSAI's ranges."]      # Sushil's change 3
    assert n["all"]["button"] == "See all 27" and len(n["all"]["rows"]) == 27
    assert sum(1 for r in n["all"]["rows"] if r["text"].startswith("Protein:")) == 1
    # Sushil's change 5: folic acid left out of the count (FSSAI's table is in DFE).
    assert n["all"]["after"] == (
        "Not compared: Saturated Fat, Trans Fat, Total Sugars, Added Sugars and Energy Value (FSSAI's table has no "
        "per 100 g row for them) and Folic acid (FSSAI's table gives folate as dietary folate equivalents).")
    assert not [r for r in n["all"]["rows"] if r["id"] == "folic_acid"]
    assert good["additives"]["lines"] == ["The list prints no INS numbers."]
    no = good["notices"]
    assert no["lines"] == [
        "Found on the pack: \"IMPORTANT NOTICE\", the mother's milk notice on the front, the storage statement.",
        "We didn't see 4 more notices FSSAI's rules ask for on these 2 photos. Tins and boxes often print them on a side."]
    assert [x["basis"] for x in no["which"]["items"]] == ["4(1)(b), PDF p. 5", "4(1)(c), PDF p. 5",
                                                          "4(1)(d), PDF p. 5", "4(6), PDF p. 6"]
    assert no["side"]["button"] == "Photograph the side" and no["side"]["photos"] == 2 and no["side"]["sides"] == 0
    assert no["side"]["missing"] == ["health_worker", "not_sole", "preparation", "boiled_water"]
    assert "compare_button" not in s and "compare" not in s["parts"]               # D-202: one pack at a time
    # The baby's card: no duplicate sugar line (Sushil's change 1); nothing else applies here.
    assert s["people"] == [] or all(not any("Sugar is" in f["text"] for f in p.get("child_facts") or [])
                                    for p in s["people"])
    assert "compare_input" not in j                                                # D-202: nothing for Compare
    assert_clean(list(strings(s)), "amulspray")
    assert infant_hits(s, printed=[NOTICE]) == []


def test_an_infant_result_never_uses_an_adult_daily_intake(infant_on):
    s = amulspray(key="amul-rda")["screen"]
    assert not ADULT_INTAKE.search(_texts(s)), ADULT_INTAKE.search(_texts(s))
    ours = {k: v for k, v in vars(screen).items() if k.startswith("INFANT_")}
    assert not ADULT_INTAKE.search(json.dumps(ours, default=str))


def test_d201s_five_words_stay_out_of_an_infant_result(infant_on):
    for word in ("high", "too much", "fails", "not allowed", "violation"):
        assert word in [w.lower() for w in infant_hits(word)]           # the lint knows each one
    s = amulspray(key="amul-words")["screen"]
    assert infant_hits(s, printed=[NOTICE]) == []
    for w in ("within", "above", "below"):                              # D-140 part 4's words stay out too
        assert not re.search(rf"\b{w}\b", _texts(s["infant"])), w


# ---------------------------------------------------------------- the shapes a pack can take

ALL_INSIDE = [("Protein", "12 g"), ("Total Fat", "20 g"), ("Carbohydrates", "55 g"), ("Iron", "5 mg")]


def test_a_pack_with_nothing_outside_its_range_has_no_worth_card(infant_on):
    v = with_table(infant("infant_formula", ingredients=["Skimmed milk", "Lactose", "Vegetable oil", "Minerals"]),
                   ALL_INSIDE)
    s = scan(v, key="inside", ocr=table_text(ALL_INSIDE))["screen"]
    assert "worth" not in s["infant"]
    assert _blocks(s)["nutrients"]["lines"] == ["All 4 nutrients we compared are inside FSSAI's ranges."]
    assert _blocks(s)["nutrients"]["all"]["button"] == "See all 4"


def test_no_added_sugar_printed_and_none_on_the_list_says_nothing_about_sugar(infant_on):
    rows = ALL_INSIDE + [("Total Sugars", "52 g"), ("Added Sugars", "0 g")]
    v = with_table(infant("infant_formula", ingredients=["Skimmed milk", "Lactose", "Vegetable oil", "Minerals"]), rows)
    s = scan(v, key="nosugar", ocr=table_text(rows))["screen"]
    assert "worth" not in s["infant"]
    # Only the "Not compared" fold names the printed sugars rows; no line says anything about sugar.
    assert not [x for b in s["infant"]["good"]["blocks"] for x in b["lines"] if "sugar" in x.lower()]
    assert infant_lens.sugar({}, ["Skimmed milk", "Lactose"], "")["positions"] == []


def test_an_added_sugar_under_two_names_names_both(infant_on):
    v = infant("processed_cereal", ingredients=["Rice flour", "Sugar", "Honey", "Milk solids"])
    [line] = scan(v, key="2sugars")["screen"]["infant"]["worth"]["items"]
    assert line["text"] == "Sugar is the 2nd of 4 ingredients. The list also names honey."


def test_a_min_only_row_reads_at_least_and_its_bar_runs_on(infant_on):
    rows = [("Alpha Linolenic Acid", "200 mg"), ("Protein", "12 g")]
    v = with_table(infant("infant_formula", ingredients=["Skimmed milk", "Lactose", "Vegetable oil"]), rows)
    s = scan(v, key="minonly", ocr=table_text(rows))["screen"]
    [ala] = s["infant"]["worth"]["items"]
    assert ala["text"] == "Alpha Linolenic Acid: 200 mg per 100 g. FSSAI's range: at least 250 mg."
    assert ala["bar"]["high"] is None and ala["bar"]["high_text"] is None
    assert ala["bar"]["low_text"] == "at least 250 mg" and ala["bar"]["scale"][1] > 250
    assert _blocks(s)["nutrients"]["lines"] == ["1 of 2 nutrients we compared is inside FSSAI's ranges."]
    bar = screen.infant_bar(300.0, 250.0, None, "mg")
    assert bar["scale"][0] < 250 < 300 < bar["scale"][1]


def test_the_range_bar_is_numbers_only_never_a_band():
    bar = screen.infant_bar(22.0, 10.0, 16.0, "g")
    assert set(bar) == {"value", "low", "high", "scale", "value_text", "low_text", "high_text"}
    for word in ("band", "zone", "tone", "colour", "color", "good", "bad", "red", "green"):
        assert word not in json.dumps(bar)
    css = open(os.path.join(HERE, "..", "web", "app.css"), encoding="utf-8").read()
    block = css[css.index("D-201"):]
    assert "--red" not in block and "--green" not in block and "--amber" not in block


# ---------------------------------------------------------------- the side photo

def _jpeg():
    """A real photo: /side-photo checks the file as the scan does (D-103's photo check)."""
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((800, 600), 60).convert("RGB").save(buf, "JPEG")
    return buf.getvalue()


SIDE_1, SIDE_2 = _jpeg(), _jpeg()
SIDE_TEXT_1 = ("IMPORTANT NOTICE Use only on the advice of a health worker as to the need for its use. "
               "Infant milk substitute is not the sole source of nourishment of an infant.")
SIDE_TEXT_2 = ("Warning/Caution: Careful and hygienic preparation of infant foods is most essential for health. "
               "Warning: Boiled and cooled water shall be used to prepare this product.")


def side(photo, block, texts, **kw):
    data = {"found": json.dumps(block["side"]["found"]), "missing": json.dumps(block["side"]["missing"]),
            "photos": str(block["side"]["photos"]), "sides": str(block["side"]["sides"]), **kw}
    with cloud_vision.replaying(texts):
        return c.post("/side-photo", files={"photo": ("s.jpg", photo, "image/jpeg")}, data=data)


def test_a_side_photo_finds_2_of_4_then_the_other_2(infant_on):
    block = _blocks(amulspray(key="amul-side")["screen"])["notices"]
    r = side(SIDE_1, block, {cloud_vision.digest(SIDE_1): SIDE_TEXT_1})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["read"] is True and [f["id"] for f in j["found"]] == ["health_worker", "not_sole"]
    assert j["photos"] == 3 and j["sides"] == 1
    block = j["notices"]
    assert block["lines"] == [
        "Found on the pack: \"IMPORTANT NOTICE\", the mother's milk notice on the front, the health worker statement, "
        "the sole source warning, the storage statement.",
        "We didn't see 2 more notices FSSAI's rules ask for on these 3 photos. Tins and boxes often print them on a side."]
    assert block["side"]["button"] == "Photograph another side" and block["side"]["missing"] == ["preparation",
                                                                                                "boiled_water"]
    r = side(SIDE_2, block, {cloud_vision.digest(SIDE_2): SIDE_TEXT_2})
    j = r.json()
    assert [f["id"] for f in j["found"]] == ["preparation", "boiled_water"] and j["sides"] == 2
    assert j["notices"]["lines"] == [
        "Found on the pack: \"IMPORTANT NOTICE\", the mother's milk notice on the front, the health worker statement, "
        "the sole source warning, the hygienic preparation warning, the storage statement, the boiled water warning."]
    assert "side" not in j["notices"] and "which" not in j["notices"]
    assert_clean(list(strings(j["notices"])), "side photo")
    assert infant_hits(j["notices"]) == []


def test_a_side_photo_that_finds_nothing_new_says_so_and_a_third_is_refused(infant_on):
    block = _blocks(amulspray(key="amul-side2")["screen"])["notices"]
    j = side(SIDE_1, block, {cloud_vision.digest(SIDE_1): "Net weight 400 g. Best before 18 months."}).json()
    assert j["found"] == [] and j["read"] is True
    assert j["notices"]["lines"][-1] == "We didn't find more of them on that photo."
    assert j["notices"]["lines"][1].startswith("We didn't see 4 more notices FSSAI's rules ask for on these 3 photos.")
    j = side(SIDE_1, j["notices"], {cloud_vision.digest(SIDE_1): "Net weight 400 g."}).json()
    assert j["sides"] == 2 and "side" not in j["notices"]                      # at most two
    r = side(SIDE_1, {"side": {**block["side"], "sides": 2}}, {cloud_vision.digest(SIDE_1): SIDE_TEXT_1})
    assert r.status_code == 422 and r.json()["error"] == "side_limit"


def test_a_side_photo_that_cant_be_read_asks_again_and_counts_nothing(infant_on, monkeypatch):
    block = _blocks(amulspray(key="amul-side3")["screen"])["notices"]
    monkeypatch.setattr(main, "SIDE_WAIT_S", 0.01)
    monkeypatch.setattr(main.ocr_check, "result_of", lambda read, ings: {"available": False, "reason": "deadline"})
    j = side(SIDE_1, block, {}).json()
    assert j["read"] is False and j["found"] == [] and j["photos"] == 2 and j["sides"] == 0
    assert j["notices"]["lines"][-1] == "We couldn't read that photo. Try again in good light."
    assert j["notices"]["side"]["button"] == "Photograph the side"


def test_the_side_photo_reads_with_tesseract_when_vision_is_off(infant_on, monkeypatch):
    block = _blocks(amulspray(key="amul-side4")["screen"])["notices"]
    monkeypatch.setattr(main, "SIDE_WAIT_S", 0.01)
    monkeypatch.setattr(main.ocr_check, "result_of", lambda read, ings: {
        "available": True, "reader": "tesseract", "ocr_text": SIDE_TEXT_2, "passes": 2})
    j = side(SIDE_1, block, {}).json()
    assert [f["id"] for f in j["found"]] == ["preparation", "boiled_water"]


def test_the_side_photo_route_checks_what_it_is_sent(infant_on):
    block = _blocks(amulspray(key="amul-side5")["screen"])["notices"]
    for bad in ({"found": "not json"}, {"missing": "[]"}, {"missing": '["no_such_statement"]'},
                {"found": '["storage"]', "missing": '["storage"]'}, {"photos": "0"}):
        r = side(SIDE_1, block, {}, **bad)
        assert r.status_code == 422 and r.json()["error"] == "bad_notices", bad
    r = c.post("/side-photo", data={"missing": '["boiled_water"]'})
    assert r.status_code == 422 and r.json()["error"] == "no_photo"


def test_the_side_photo_route_is_off_with_the_switch(infant_off):
    r = c.post("/side-photo", files={"photo": ("s.jpg", SIDE_1, "image/jpeg")}, data={"missing": '["boiled_water"]'})
    assert r.status_code == 404


def test_the_front_notice_goes_out_under_a_neutral_id():
    assert infant_lens.public_id("mothers_milk") == "front_notice"
    assert infant_lens.private_id("front_notice") == "mothers_milk"
    assert infant_lens.public_id("storage") == infant_lens.private_id("storage") == "storage"
    assert "mothers_milk" not in infant_lens.SIDE_IDS                     # never looked for on a side


def test_side_found_looks_only_for_what_is_missing():
    assert infant_lens.side_found(SIDE_TEXT_1, ["not_sole"]) == ["not_sole"]
    assert infant_lens.side_found(SIDE_TEXT_1, ["boiled_water"]) == []
    assert infant_lens.side_found("MOTHER'S MILK IS BEST FOR YOUR BABY", ["mothers_milk"]) == []
    assert infant_lens.side_found("", ["not_sole"]) == []


# ---------------------------------------------------------------- Compare

def test_infant_packs_are_never_compared(infant_on):
    # D-202 (Sushil, 2026-10-14): "for infants we will not keep any compare only scan for 1 product each".
    a = amulspray(key="amul-cmp")
    rows = ALL_INSIDE + [("Total Sugars", "52 g"), ("Added Sugars", "0 g")]
    b = scan(with_table(infant("infant_formula", ingredients=["Skimmed milk", "Lactose", "Vegetable oil"],
                               statements=STATEMENTS + [BOILED]), rows), key="cmp-b", ocr=table_text(rows))
    r = compare(_packs(a, b))
    assert r.status_code == 422 and r.json()["reason"] == "infant_food"
    assert r.json()["detail"] == "We check foods for infants one pack at a time."
    text = _without_the_notice(json.dumps(r.json())).lower()
    assert "mother" not in text and "breast" not in text


# ---------------------------------------------------------------- the child card (Sushil's change 1)

def test_the_child_card_on_an_infant_pack_keeps_its_age_lines_without_the_sugar_one(infant_on):
    # An infant cereal with honey and a 6 month old: the age line ICMR-NIN gives for the baby's
    # age stays (salt); the sugar line is the result's own. The honey line stays held with
    # breastfeeding guideline 3 (Sushil's "Hold it", 2026-10-13).
    v = infant("processed_cereal", ingredients=["Rice flour", "Sugar", "Honey", "Iodised salt", "Milk solids"])
    s = scan(v, key="honey", profiles=BABY)["screen"]
    [p] = s["people"]
    assert p["ref"] == "p1" and p["status"] == "worth_knowing"
    assert [f["source"]["ref"] for f in p["child_facts"]] == ["salt"]
    assert p["child_facts"][0]["text"] == ("ICMR-NIN's dietary guidelines say \"Limit use of salt in complementary "
                                           "food preparations\".")
    assert not any("Sugar is" in f["text"] for f in p["child_facts"])
    assert "breastfeed" not in json.dumps(s).lower()
    assert s["infant"]["worth"]["items"][0]["text"] == ("Sugar is the 2nd of 5 ingredients. The list also names "
                                                        "honey.")


def test_the_child_card_on_a_food_is_unchanged(infant_on):
    v = reading(["Wheat flour", "Sugar", "Iodised salt"], [st("Glucose biscuits", "front")])
    s = scan(v, key="food-kid", profiles=BABY)["screen"]
    texts = [f["text"] for p in s["people"] for f in p.get("child_facts") or []]
    assert any(t.startswith("Sugar is the 2nd ingredient") for t in texts)


# ---------------------------------------------------------------- the pack's name (Sushil's change 2)

NAMES = [({"brand": "Amulspray", "name": "Amulspray"}, "Amulspray"),
         ({"brand": "Amul", "name": "Amul Butter"}, "Amul Butter"),
         ({"brand": "AMUL", "name": "amul  butter", "variant": "500 g"}, "amul  butter 500 g"),
         ({"brand": "Amul Spray", "name": "Amulspray Infant Milk Food"}, "Amulspray Infant Milk Food"),
         ({"brand": "Britannia", "name": "Good Day"}, "Britannia Good Day"),
         ({"brand": "Britannia", "name": "Good Day", "variant": "Cashew"}, "Britannia Good Day Cashew"),
         ({"brand": "Tata", "name": None}, "Tata"),
         ({"brand": None, "name": "Rusk"}, "Rusk"),
         ({}, "Unnamed pack"), (None, "Unnamed pack")]


def test_the_brand_shows_once_and_no_food_loses_it():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    src = open(os.path.join(HERE, "..", "web", "app.js"), encoding="utf-8").read()
    fn = re.search(r"^function productName\(product\) \{.*?^\}", src, re.M | re.S).group(0)
    script = fn + "\nconst cases = " + json.dumps([p for p, _ in NAMES]) + ";\n" + \
        "console.log(JSON.stringify(cases.map(productName)));"
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [want for _, want in NAMES]
    # Every place a pack is named goes through it: the result, Your scans, Compare and Share.
    assert src.count("productName(h.product)") >= 10 and "productName(x.product)" in src
    assert not re.search(r"\.brand\b(?!\s*&&\s*!)", src.replace("p.brand", ""))

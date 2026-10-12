"""
D-200 (Sushil, 2026-10-12): infant results to users behind INSIDELABEL_INFANT_TO_USERS, and
Compare for supplements and infant foods, side by side with no pick.

- Switch off: every route answers exactly as D-140's shadow did before D-200. The answers
  were recorded from main 636386b into fixtures/infant_shadow_before.json (SCENARIOS below,
  run there) and must come out byte for byte the same.
- Switch on: an infant result for each product type and with none; regulation 4's statements
  found or not found; a forbidden word; Compare between infant packs and between supplements
  with no winner words; each mixed refusal; the shop list and Share.
- The hard lines that stay with "Everything": nothing beside mother's milk (IMS Act 3(b)), no
  score, grade or band, special_medical unchanged, no breastfeeding line, and the infant words
  ("safe", "best", "recommended", "healthy", "suitable for your baby"; tests/test_wording.py).
"""
import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from test_pack_kind import FAM, INVENTED, reading, st
from test_wording import assert_clean, infant_hits, strings

from insidelabel.api import main
from insidelabel.core import pack_kind
from insidelabel.extraction.providers import cloud_vision
from insidelabel.lenses import screen

HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(HERE, "fixtures", "infant_shadow_before.json")
c = TestClient(main.app)
NOTICE = "MOTHER'S MILK IS BEST FOR YOUR BABY"
STATEMENTS = [st("IMPORTANT NOTICE", "front"), st(NOTICE, "front"),
              st("Infant food shall be introduced only after the age of six months and up to the age of two years"),
              st("Use only on the advice of a health worker as to the need for its use and the proper method of its use"),
              st("Infant food is not the sole source of nourishment of an infant"),
              st("Warning/Caution: Careful and hygienic preparation of infant foods is most essential for health"),
              st("Store in a cool and dry place in an air tight container")]
BOILED = st("Warning: Boiled and cooled water shall be used to prepare this product and any leftover product "
            "must be discarded to reduce the risk of infection")
TYPES = {"infant_formula": "Infant Formula", "follow_up_formula": "Follow Up Formula",
         "milk_cereal": "Milk Cereal Based Complementary Food",
         "processed_cereal": "Processed Cereal Based Complementary Food",
         "traditional": "Traditional Food for Infants"}
BABY = [{"ref": "me", "age": "adult", "avoid": []}, {"ref": "p1", "age": "baby", "avoid": ["milk"]}]


def scan(v, key="x", profiles=FAM, ocr=""):
    """/scan with a recorded answer and a recorded second reading of the back photo."""
    photo = b"\xff\xd8\xff\xe0" + key.encode()
    text = ("INGREDIENTS: " + ", ".join(v["ingredients"]) + ". " +
            " ".join(s["text"] for s in v.get("pack_statements") or []) + " " + ocr)
    files = {"back": ("b.jpg", photo, "image/jpeg")}
    if v["front_status"] == "read":
        files["front"] = ("f.jpg", photo + b"f", "image/jpeg")
    with cloud_vision.replaying({cloud_vision.digest(photo): text}):
        r = c.post("/scan", files=files, data={"replay": json.dumps(v), "profiles": json.dumps(profiles),
                                                "pairing_confirmed": "true"})
    assert r.status_code == 200, r.text
    return r.json()


def compare(packs, **kw):
    return c.post("/compare", json={"packs": packs, "age": "kid", **kw})


def infant(type_id=None, ingredients=("Rice flour", "Milk solids", "Minerals", "Vitamins"), statements=STATEMENTS,
           extra=(), **kw):
    words = list(statements) + ([st(TYPES[type_id], "front")] if type_id else []) + list(extra)
    return reading(list(ingredients), words, allergen="Contains milk.", **kw)


def _strip(j):
    return {k: v for k, v in j.items() if k not in ("request_id", "scan_id")}


def scenarios():
    """Every route an infant pack takes, as answered with the switch off (recorded on main)."""
    out = {}
    for t in [*TYPES, None]:
        out[f"scan:{t}"] = _strip(scan(infant(t, extra=[st("ENERGY FOOD", "front")]), key=f"s-{t}"))
    v = infant("milk_cereal", front="not_provided")
    v["image_content"] = {"back": "screen", "front": "not_provided"}
    out["scan:screen"] = _strip(scan(v, key="screen"))
    out["scan:special_medical"] = _strip(scan(reading(*INVENTED["hypoallergenic"][:2]), key="sm"))
    food = {"id": "f", "name": "Rusk", "ingredients": ["Wheat flour", "Sugar"]}
    baby = {"id": "i", "name": "Cereal", "ingredients": ["Rice flour", "Milk solids"]}
    words = [{"text": NOTICE, "face": "front"}]
    for name, packs in {"client_kind": [food, {**baby, "kind": "infant"}],
                        "printed": [food, {**baby, "pack_statements": words}],
                        "both_infant": [{**food, "kind": "infant"}, {**baby, "kind": "infant"}]}.items():
        r = compare(packs)
        out[f"compare:{name}"] = {"status": r.status_code, "body": _strip(r.json())}
    return out


# ---------------------------------------------------------------- the switch

def test_the_switch_reads_on_when_unset_and_off_for_anything_but_on(monkeypatch):
    monkeypatch.setattr(pack_kind, "INFANT_TO_USERS", None)
    monkeypatch.delenv("INSIDELABEL_INFANT_TO_USERS", raising=False)
    assert pack_kind.infant_to_users()                                   # Sushil's choice: on by default
    for value, on in (("on", True), ("ON", True), ("off", False), ("no", False), ("", False), ("of", False)):
        monkeypatch.setenv("INSIDELABEL_INFANT_TO_USERS", value)
        assert pack_kind.infant_to_users() is on, value


def test_switch_off_every_route_answers_exactly_as_before_d200(infant_off):
    before = json.load(open(BEFORE, encoding="utf-8"))
    now = json.loads(json.dumps(scenarios()))
    assert sorted(now) == sorted(before)
    for key in before:
        assert json.dumps(now[key], sort_keys=True) == json.dumps(before[key], sort_keys=True), key


def test_switch_off_hides_share_on_an_infant_result_only():
    # D-200 (Sushil, 2026-10-12): the one change with the switch off. Share shows unless the result
    # is an infant pack's and its parts don't list "share" (the shadow's parts never do).
    src = open(os.path.join(HERE, "..", "web", "app.js"), encoding="utf-8").read()
    assert 'return s?.kind?.code !== "infant" || (s.parts || []).includes("share");' in src
    assert "canShare(h.screen) && el(\"button\"" in src
    assert "share" not in pack_kind.PARTS["infant"] and "share" in pack_kind.TABLE["kinds"]["infant"]["to_users"]["parts"]


# ---------------------------------------------------------------- the infant result

@pytest.mark.parametrize("type_id", [*TYPES, None])
def test_an_infant_result_for_each_product_type_and_with_none(type_id, infant_on):
    j = scan(infant(type_id), key=f"t-{type_id}")
    s = j["screen"]
    assert j["pack_kind"]["code"] == "infant" and j["verdict"] is None and list(j)[0] == "allergens"
    assert s["kind"]["lines"][0] == screen.INFANT_TEXT
    sections = {x["id"] for x in s["sections"]}
    if type_id is None:
        assert s["kind"]["lines"][1] == screen.INFANT_NO_TYPE
        assert sections == {"statements"} and j["compare_input"]["type"] is None
    else:
        assert s["kind"]["lines"][1] == (f"The pack's name says \"{TYPES[type_id]}\", so we use FSSAI's rules for "
                                         f"{screen.INFANT_TYPE_WORDS[type_id]}.")
        assert {"statements", "additives"} <= sections and j["compare_input"]["type"]["id"] == type_id
    assert_clean(list(strings(s)), f"infant {type_id}")
    assert not infant_hits(s, printed=[NOTICE])


def test_regulation_4s_statements_found_and_not_found(infant_on):
    [sec] = [x for x in scan(infant("processed_cereal"), key="r4")["screen"]["sections"] if x["id"] == "statements"]
    assert sec["lines"][0].startswith("FSSAI's rules for infant foods ask the label for \"Warning: Boiled and cooled")
    assert sec["lines"][-1] == ("Found on the pack, as the rules ask: \"IMPORTANT NOTICE\", the mother's milk notice on "
                                "the front, the six months statement, the health worker statement, the sole source "
                                "warning, the hygienic preparation warning, the storage statement.")
    sec = scan(infant("processed_cereal", statements=STATEMENTS + [BOILED]), key="r4b")["screen"]["sections"][0]
    assert len(sec["lines"]) == 1 and sec["lines"][0].endswith("the boiled water warning.")
    # The front notice not printed: named, never quoted ("best" only as printed on the pack).
    sec = scan(infant("processed_cereal", statements=[s for s in STATEMENTS if s["text"] != NOTICE]),
               key="r4c")["screen"]["sections"][0]
    assert any("the notice about mother's milk that regulation 4(1)(a) asks for on the front" in t for t in sec["lines"])
    assert "BEST" not in json.dumps(sec).upper()
    # Only one face read: nothing is "not found".
    sec = scan(infant("processed_cereal", front="not_provided"), key="r4d")["screen"]["sections"][0]
    assert sec["lines"] == [screen.INFANT_PARTIAL]


def test_a_forbidden_word_as_printed(infant_on):
    s = scan(infant("milk_cereal", extra=[st("The complete Energy Food", "front")]), key="w")["screen"]
    [t] = [t for t in s["tiles"] if t["id"].startswith("word-")]
    assert t["title"] == '"Energy Food" on the pack'
    d = s["details"][t["id"]]
    assert d["on_the_label"] == "The complete Energy Food" and d["sources"][0]["page"] == "4(2), PDF p. 6"


def test_5_1_hydrogenated_fat_and_additives_by_type(infant_on):
    ings = ["Rice flour", "Milk solids", "Vanilla flavour", "Partially hydrogenated vegetable oil",
            "Emulsifier (INS 472e)"]
    tiles = {t["id"]: t for t in scan(infant("follow_up_formula", ingredients=ings), key="h")["screen"]["tiles"]}
    assert tiles["free-vanillaflavour"]["chip"] == "FSSAI's infant rules leave out added flavours"
    assert "hydro-partiallyhydrogenatedvegetableoil" in tiles
    tiles = {t["id"] for t in scan(infant("traditional", ingredients=ings), key="h2")["screen"]["tiles"]}
    assert not [t for t in tiles if t.startswith("hydro-")]                 # 11 says nothing about it
    tiles = {t["id"] for t in scan(infant(None, ingredients=ings), key="h3")["screen"]["tiles"]}
    assert "free-vanillaflavour" in tiles and not [t for t in tiles if t.startswith(("hydro-", "iadd-"))]


# ---------------------------------------------------------------- Compare

WINNER_WORDS = re.compile(r"\b(better|best|winner|top|recommended|ranked?|first choice|pick of these|choose)\b", re.I)


def _keys(kind):
    from insidelabel.lenses import side_by_side          # imported here: the recording ran on main, before it
    return side_by_side.KEYS[kind]


def _packs(*bodies):
    return [{"id": f"p{i}", "name": f"Pack {i}", "ingredients": b["extracted"]["ingredients"],
             "allergen_statement": b["extracted"].get("allergen_statement"), "kind": b["pack_kind"]["code"],
             "pack_statements": b["extracted"].get("pack_statements") or [], "facts": b.get("compare_input")}
            for i, b in enumerate(bodies)]


def test_infant_against_infant_is_side_by_side_with_no_pick(infant_on):
    a = scan(infant("processed_cereal", ingredients=["Wheat flour", "Milk solids", "Vanilla flavour"]), key="ca")
    b = scan(infant("milk_cereal", statements=STATEMENTS + [BOILED]), key="cb")
    r = compare(_packs(a, b), avoid=["milk"], who="{name}")
    assert r.status_code == 200
    j = r.json()
    assert j["outcome"] == "side_by_side" and j["kind"] == "infant"
    for key in ("best", "tie", "why_best", "others", "blocked", "summary"):
        assert key not in j, key
    assert [p["id"] for p in j["packs"]] == ["p0", "p1"]                       # the order sent, nothing else
    for p in j["packs"]:
        assert [row["key"] for row in p["rows"]] == list(_keys("infant"))
        assert p["allergens"][0]["state"] == "contains"
    text = json.dumps({k: j[k] for k in ("heading", "note", "packs")})
    assert not WINNER_WORDS.search(text.replace("We don't name a pick", ""))
    assert "We don't name a pick between infant foods" in j["note"]
    assert_clean(list(strings(j)), "infant compare")
    assert not infant_hits(j)


def test_supplement_against_supplement_is_side_by_side_with_no_winner_and_no_child_line(infant_off):
    from test_supplements import TABLET_COMP
    def sup(key, daily):
        v = reading(["Calcium carbonate", "Ascorbic acid", "Microcrystalline cellulose"],
                    [st("HEALTH SUPPLEMENT", "front"), st("NOT FOR MEDICINAL USE"), st(daily)])
        v["composition"] = json.loads(json.dumps(TABLET_COMP))
        ocr = " ".join(f"{r['name']} {r.get('amount')}" for r in v["composition"]["rows"])
        return scan(v, key=key, profiles=[{"ref": "p1", "age": "toddler", "avoid": []}], ocr=ocr)
    r = compare(_packs(sup("s1", "Take 1 tablet daily"), sup("s2", "Take 2 tablets twice a day")), age="toddler")
    assert r.status_code == 200
    j = r.json()
    assert j["outcome"] == "side_by_side" and j["kind"] == "supplement"
    for key in ("best", "tie", "why_best"):
        assert key not in j
    for p in j["packs"]:
        assert [row["key"] for row in p["rows"]] == list(_keys("supplement"))
    text = json.dumps({k: j[k] for k in ("heading", "note", "packs")})       # sources are titles, not our words
    assert not WINNER_WORDS.search(text.replace("We don't name a pick", ""))
    assert "RDA" in text and not re.search(r"RDA[^.]{0,20}limit|limit[^.]{0,20}RDA", text)    # D-139
    for word in ("child", "children", "2 to 5", "medical advice"):                          # 5(10)
        assert word not in text
    assert_clean(list(strings(j)), "supplement compare")


@pytest.mark.parametrize("kinds,detail", [
    (("supplement", "food"), "We compare a supplement only with other supplements."),
    (("infant", "food"), "We compare an infant food only with other infant foods."),
    (("supplement", "infant"), "We compare an infant food only with other infant foods."),
])
def test_a_mixed_compare_is_refused_with_its_own_sentence(kinds, detail, infant_on):
    packs = [{"id": k, "name": k, "ingredients": ["Rice flour"], "kind": k} for k in kinds]
    r = compare(packs)
    assert r.status_code == 422 and r.json()["reason"] == "mixed_kinds" and r.json()["detail"] == detail


def test_food_compare_is_unchanged_by_d200(infant_on):
    packs = [{"id": "a", "name": "A", "ingredients": ["Whole wheat flour", "Sugar"]},
             {"id": "b", "name": "B", "ingredients": ["Refined wheat flour", "Sugar", "Colour (INS 102)"]}]
    j = compare(packs).json()
    assert j["outcome"] == "best" and j["best"] == "a"


def test_shop_list_and_share_for_an_infant_pack(infant_on):
    v = infant("milk_cereal", front="not_provided")
    v["image_content"] = {"back": "screen", "front": "not_provided"}
    s = scan(v, key="shop")["screen"]
    assert s["shop_list"] is True and {"compare", "shop_list", "share"} <= set(s["parts"])
    src = open(os.path.join(HERE, "..", "web", "app.js"), encoding="utf-8").read()
    assert "if (h.pack) put(shopListButton(s, h), resultNext(s, h), reportLink(h));" in src
    assert "facts: body.compare_input || null" in src


# ---------------------------------------------------------------- the hard lines

def _without_the_notice(text):
    return text.replace(NOTICE, "").replace("the mother's milk notice on the front", "").replace(
        "the notice about mother's milk that regulation 4(1)(a) asks for on the front", "")


def test_nothing_sets_an_infant_food_beside_mothers_milk(infant_on):
    # IMS Act 3(b): mother's milk only in the notice the pack prints (or its name), never as a
    # reference or a Compare column.
    a = scan(infant("infant_formula"), key="m1")
    b = scan(infant("follow_up_formula", statements=[s for s in STATEMENTS if s["text"] != NOTICE]), key="m2")
    j = compare(_packs(a, b)).json()
    for out in (a["screen"], b["screen"], j):
        text = _without_the_notice(json.dumps(out)).lower()
        assert "mother" not in text and "breast" not in text
    assert len(j["packs"]) == 2 and all(p["id"] in ("p0", "p1") for p in j["packs"])


def test_no_score_grade_or_band_for_an_infant_pack_or_a_supplement(infant_on):
    for v in (infant("processed_cereal"), reading(*INVENTED["multivitamin_tablet"][:2])):
        j = scan(v, key="sg" + v["pack_statements"][0]["text"][:4], profiles=BABY)
        # D-140's age band question is about a profile, not the pack; it isn't on these results.
        assert "band_question" not in j["screen"]
        text = json.dumps(j["screen"]).lower()
        for word in ("score", "grade", "band"):
            assert not re.search(rf"\b{word}\b", text), word
    j = compare(_packs(scan(infant("milk_cereal"), key="sg1"), scan(infant("processed_cereal"), key="sg2"))).json()
    assert not re.search(r"\b(score|grade|band)\b", json.dumps(j).lower())


def test_special_medical_stays_allergens_and_its_own_statement(infant_off):
    off = _strip(scan(reading(*INVENTED["hypoallergenic"][:2]), key="smx"))
    pack_kind.INFANT_TO_USERS = True
    try:
        on = _strip(scan(reading(*INVENTED["hypoallergenic"][:2]), key="smx"))
    finally:
        pack_kind.INFANT_TO_USERS = False
    assert on == off and on["screen"]["kind"]["lines"] == [screen.KIND_TEXT["special_medical"]]
    assert "compare" not in on["screen"]["parts"] and "compare_input" not in on
    r = compare([{"id": "a", "name": "A", "ingredients": ["Whey"], "kind": "special_medical"},
                 {"id": "b", "name": "B", "ingredients": ["Whey"], "kind": "special_medical"}])
    assert r.status_code == 422 and r.json()["reason"] == "special_medical"


def test_the_breastfeeding_line_stays_held(infant_on):
    s = scan(infant("processed_cereal"), key="bf")["screen"]
    assert "breastfeeding" not in s and "breastfeed" not in json.dumps(s).lower()
    assert "exclusive breastfeeding" not in json.dumps(screen.__dict__.get("INFANT_TEXT"))

"""
The result screen block (D-060-D-066, D-074). Labels are invented.

What the app renders comes from `screen`; these tests pin the order, the
states that must never appear, and that profile names stay on the device.
"""
import base64
import json
import re

from fastapi.testclient import TestClient

from insidelabel.api.main import app
from insidelabel.lenses import screen

c = TestClient(app)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}

PLAIN = ["Whole wheat flour", "Groundnut oil", "Salt", "Cumin"]
BISCUIT = ["Refined wheat flour (Maida)", "Sugar", "Liquid glucose", "Milk solids",
           "Preservative (INS 211)", "Emulsifier (INS 322)", "Maltodextrin"]
FAMILY = [{"ref": "me", "age": "adult", "avoid": ["peanut"]},
          {"ref": "p1", "age": "toddler", "avoid": ["milk"]},
          {"ref": "p2", "age": "kid", "avoid": []}]


def vision(ingredients, **kw):
    v = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": "Contains wheat, milk.",
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5},
    }
    v.update(kw)
    return json.dumps(v)


def scan(ingredients, profiles=FAMILY, **kw):
    data = {"replay": vision(ingredients, **kw)}
    if profiles is not None:
        data["profiles"] = json.dumps(profiles)
    return c.post("/scan", files=BACK, data=data)


def keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys(v)


def test_people_first_and_allergens_still_first_key():
    j = scan(BISCUIT).json()
    assert next(iter(j)) == "allergens"                              # D-060
    assert list(j["screen"])[:3] == ["state", "people", "headline"]
    # The top-level block covers every profile's avoid list.
    assert j["allergens"]["avoid"] == ["peanut", "milk"]
    people = {p["ref"]: p for p in j["screen"]["people"]}
    assert people["p1"]["status"] == "contains"
    assert people["p1"]["line"] == "Contains milk. It's on {name}'s avoid list."
    # D-126: the line names what was checked.
    assert people["me"]["line"] == "Peanut: not listed in the ingredients or the allergen line."


def test_names_never_reach_the_server():                            # D-074
    bad = [{"ref": "p1", "age": "kid", "avoid": [], "name": "Aarav"}]
    r = scan(PLAIN, profiles=bad)
    assert r.status_code == 422 and r.json()["error"] == "bad_profiles"
    four = [{"ref": f"p{i}", "age": "kid", "avoid": []} for i in range(4)]
    assert scan(PLAIN, profiles=four).status_code == 422
    assert scan(PLAIN, profiles=[{"ref": "Aarav Sharma", "age": "kid"}]).status_code == 422


def test_no_score_in_the_screen():                                  # D-064
    s = scan(BISCUIT).json()["screen"]
    assert not {"score", "grade", "display_score"} & set(keys(s))


def test_headline_is_a_finding_with_its_source():                   # D-061
    s = scan(BISCUIT).json()["screen"]
    # D-123: where sugar sits, then its other name (was "Sugar appears under 2 names: ...").
    assert s["headline"]["text"] == "Sugar is the 2nd ingredient, and appears again as liquid glucose."
    assert s["headline"]["source"]["kind"] == "hidden_sugar"
    # Maltodextrin is added_sugar_adjacent, not a sugar name.
    assert "maltodextrin" not in s["headline"]["text"]
    assert s["band"]["label"] == "Made with industrial ingredients"  # D-063
    assert s["band"]["note"]


def test_nothing_wrong_is_a_designed_state():                       # D-062
    s = scan(PLAIN, profiles=[]).json()["screen"]
    assert s["headline"]["text"] == "No concerns found in the ingredients."
    # D-173 follow-up: one sentence says what was checked; claims are in shadow.
    assert s["checked"] is None and s["scope"].startswith("We checked the 4 ingredients on the list against ")
    assert s["worth_knowing"] == [] and s["ordinary"]["count"] == 4
    assert s["people"] == []                                        # adult, no avoid list


def test_partial_read_never_says_no_concerns():                     # D-062, gates rule 3
    s = scan(PLAIN, ingredients_status="partial").json()["screen"]
    assert "No concerns" not in s["headline"]["text"]
    assert s["band"]["code"] == "incomplete"
    assert s["retake"]
    assert all(p["status"] == "cannot_confirm" for p in s["people"] if p["ref"] in ("me", "p1"))


def test_ordinary_additives_are_grouped():                          # D-065
    s = scan(BISCUIT).json()["screen"]
    worth = [w["name"] for w in s["worth_knowing"]]
    ordinary = [a["name"] for a in s["ordinary"]["additives"]]
    assert "Sodium benzoate" in worth
    assert any("Lecithin" in n for n in ordinary) and not any("Lecithin" in n for n in worth)
    assert s["ordinary"]["text"].endswith("look ordinary.")


def test_refused_scan_names_the_problem():                          # D-036, D-037
    r = scan(PLAIN, back_status="unreadable")
    assert r.status_code == 422
    s = r.json()["screen"]
    assert s["state"] == "retake" and s["retake"] != screen.RETAKE_DEFAULT
    assert {p["status"] for p in s["people"] if p["ref"] != "p2"} == {"cannot_confirm"}


def test_kid_line_for_a_profile_without_avoid_list():
    people = {p["ref"]: p for p in scan(BISCUIT).json()["screen"]["people"]}
    assert people["p2"]["status"] == "worth_knowing"               # sugar is the 2nd ingredient
    assert "{name}" in people["p2"]["line"]


def test_empty_form_boxes_are_ignored():
    # /docs and other form tools can send every empty text box as "".
    empty = {k: "" for k in ("avoid", "who", "barcode", "device_id", "profiles")}
    r = c.post("/scan", files=BACK, data={**empty, "replay": vision(PLAIN)})
    assert r.status_code == 200 and r.json()["screen"]["state"] == "result"
    # An empty replay is not a model answer: with no photo it is "no images", not a parse error.
    r = c.post("/scan", data={**empty, "replay": ""})
    assert r.status_code == 422 and r.json()["error"] == "no_images"


def test_docs_page_prefills_nothing():
    spec = c.get("/openapi.json").json()
    ref = spec["paths"]["/scan"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    props = spec["components"]["schemas"][ref.split("/")[-1]]["properties"]
    for name in ("replay", "avoid", "who", "barcode", "device_id", "profiles"):
        assert props[name].get("examples") == [""], name       # else Swagger fills in "string"


# ---------------------------------------------------------------- additive badges (D-111)

def _adds(j):
    return {a["ins"]: a for a in j["screen"]["additives"]["items"]}


def test_each_additive_gets_a_badge_from_its_fssai_row():
    j = scan(["Wheat flour", "Sugar", "Colour (INS 102)", "Acidity regulator (INS 330)"], profiles=None).json()
    adds = _adds(j)
    assert adds["102"]["badge"] == {"kind": "worth_knowing", "text": "Worth knowing"}     # permitted, moderate
    assert adds["330"]["badge"] == {"kind": "permitted", "text": "Permitted in India"}    # GMP table
    assert j["screen"]["additives"]["title"] == "Additives on this pack (2)"
    assert "additive_alert" not in j["screen"]
    # The same items are still in the older lists, for app versions before D-111.
    assert any(w.get("ins") == "102" for w in j["screen"]["worth_knowing"])
    assert any(a.get("ins") == "330" for a in j["screen"]["ordinary"]["additives"])


def test_not_permitted_needs_a_sure_read_and_comes_first():
    ing = ["Wheat flour", "Acidity regulator (INS 330)", "Flour treatment agent (INS 924a)"]
    j = scan(ing, profiles=None).json()                                   # confidence 0.98
    items = j["screen"]["additives"]["items"]
    assert items[0]["ins"] == "924a"
    assert items[0]["badge"] == {"kind": "not_permitted", "text": "Not permitted in India"}
    alert = j["screen"]["additive_alert"]
    assert alert["text"] == "An additive on this label isn't in FSSAI's permitted list."
    assert alert["detail"].startswith('We read "INS 924a" on the label.') and alert["source"]["kind"] == "additive"

    unsure = scan(ing, profiles=None, confidence={"ingredients": 0.9, "front_claims": 0.0,
                                                  "product_identity": 0.5}).json()
    assert unsure["screen"]["state"] == "result"                         # the general gate still shows it
    b = _adds(unsure)["924a"]["badge"]
    assert b["kind"] == "worth_knowing" and "Check this number on the pack" in b["note"]
    assert "additive_alert" not in unsure["screen"]


def test_partial_read_never_says_not_permitted():
    j = scan(["Wheat flour", "Flour treatment agent (INS 924a)"], profiles=None,
             ingredients_status="partial").json()
    assert j["screen"]["state"] == "result"
    assert _adds(j)["924a"]["badge"]["kind"] == "worth_knowing"
    assert "additive_alert" not in j["screen"]


def test_no_badge_without_a_recorded_basis(monkeypatch):
    from insidelabel.core import engine
    row = dict(engine._ADDITIVE_BY_INS["330"]); row.pop("fssai_basis")
    monkeypatch.setitem(engine._ADDITIVE_BY_INS, "330", row)
    j = scan(["Wheat flour", "Acidity regulator (INS 330)"], profiles=None).json()
    assert _adds(j)["330"]["badge"] is None


def test_badge_words_stay_within_d042():
    from insidelabel.lenses import screen as sc
    text = " ".join([*sc.BADGE_TEXT.values(), sc.CHECK_NUMBER, sc.ADDITIVE_ALERT]).lower()
    for w in ("safe", "banned", "illegal", "harmful", "risk", "dangerous", "toxic"):
        assert w not in text, w


def test_permitted_cards_fold_and_cards_quote_the_label_line():
    """D-111: "Permitted" cards fold into one row; each card quotes its whole label line."""
    j = scan(["Wheat flour", "Colour (INS 102)", "Raising agent (INS 503(ii))", "Acidity regulator (INS 330)"],
             profiles=None).json()
    a = j["screen"]["additives"]
    assert [i["ins"] for i in a["items"]][0] == "102" and a["open"] == 1
    assert a["folded_text"] == "2 more additives, each permitted in India"
    assert _adds(j)["503"]["label_line"] == "Raising agent (INS 503(ii))"
    only = scan(["Wheat flour", "Acidity regulator (INS 330)"], profiles=None).json()["screen"]["additives"]
    assert only["open"] == 0 and only["folded_text"] == "1 additive, permitted in India"


# ------------------------------------------------------------------ D-123 three answers

def test_three_answers_right_under_the_headline():
    s = scan(BISCUIT).json()["screen"]
    assert list(s)[:4] == ["state", "people", "headline", "summary"]
    rows = {r["key"]: r for r in s["summary"]}
    assert [r["key"] for r in s["summary"]] == ["sugar", "processing", "additives"]
    assert rows["sugar"]["chip"] == "2nd of 7" and rows["sugar"]["tone"] == "worth"
    assert rows["sugar"]["text"] == "Also listed as liquid glucose (3rd). All are added sugar."
    assert rows["processing"]["chip"] == "Industrial"
    assert rows["additives"]["chip"] == "2 \u00b7 1 to know"
    assert rows["additives"]["text"] == ("Sodium benzoate (preservative 211) is worth knowing. "
                                         "The other one is permitted in India.")


def test_a_plain_list_says_none_found_for_all_three():
    rows = {r["key"]: r for r in scan(PLAIN, profiles=[]).json()["screen"]["summary"]}
    assert {r["chip"] for r in rows.values()} == {"None found"}
    assert all(r["tone"] == "calm" for r in rows.values())


def test_a_partial_read_never_says_none_found():                    # D-062
    rows = scan(PLAIN, ingredients_status="partial").json()["screen"]["summary"]
    assert not any(r["chip"] == "None found" for r in rows)
    assert all(r["chip"] == "Not sure" for r in rows)


def test_no_concerns_found_never_sits_under_a_finding():
    """Lotus Biscoff (2026-09-27): a sugar headline above "No concerns found"."""
    s = scan(["Wheat flour", "Sugar", "Palm oil", "Candy sugar syrup", "Salt"], profiles=[]).json()["screen"]
    assert s["headline"]["text"] == "Sugar is the 2nd ingredient, and appears again as candy sugar syrup."
    assert s["band"]["label"] == "A few things worth knowing" and s["band"]["code"] == "mixed"


def test_a_named_additive_headline_says_what_it_is():
    s = scan(["Carbonated water", "Sugar", "Preservative (INS 211)"], profiles=[]).json()["screen"]
    assert s["headline"]["text"] == "Has Sodium benzoate, a preservative."


def test_tallies_for_your_scans_are_worded_here():                 # D-123, D-091
    s = scan(BISCUIT).json()["screen"]
    assert s["tallies"] == [screen.TALLY["sugar_early"], screen.TALLY["sugar_names"],
                            screen.TALLY["industrial"], screen.TALLY["additive"]]
    assert scan(PLAIN, profiles=[]).json()["screen"]["tallies"] == []


def test_the_all_clear_line_names_each_allergen_checked():         # D-126
    fam = [{"ref": "me", "age": "adult", "avoid": ["fish", "sesame"]}]      # PLAIN has groundnut oil
    [p] = scan(PLAIN, profiles=fam).json()["screen"]["people"]
    assert p["line"] == "Fish, sesame: not listed in the ingredients or the allergen line."
    [p] = scan(PLAIN, profiles=fam, allergen_statement=None).json()["screen"]["people"]
    assert p["line"] == ("Fish, sesame: not in the ingredients. We didn't see a \"may contain\" "
                         "line in the photo, so check the pack.")


# ------------------------------------------------------------------ D-127 at a glance, words

MALIBAN = ["REFINED WHEAT FLOUR (MAIDA)", "SUGAR", "REFINED PALM OIL", "MILK SOLIDS", "WHEY", "MALTODEXTRIN",
           "IODIZED SALT", "EMULSIFIER (322 (i))", "RAISING AGENT (500 (ii))", "COLOURS (160 a(ii), 129)",
           "ACIDITY REGULATOR (270)", "NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES"]      # the gold label


def test_at_a_glance_gives_each_entry_one_type():
    g = scan(MALIBAN, profiles=[]).json()["screen"]["glance"]
    assert g["total"] == 12
    assert g["counts"] == {"worth": 1, "sugar": 1, "industrial": 3, "additive": 2, "other": 5}
    assert [e["type"] for e in g["entries"]][:3] == ["other", "sugar", "other"]
    assert g["entries"][9] == {"n": 10, "text": "COLOURS (160 a(ii), 129)", "type": "worth"}
    assert "not weight" in g["caption"]


def test_the_words_used_are_explained_and_linked():
    words = scan(MALIBAN, profiles=FAMILY).json()["screen"]["glossary"]
    assert [w["key"] for w in words] == ["sugar", "industrial", "additive", "worth", "permitted", "other",
                                          "allergen_line"]
    assert all(w["url"] == f"/how#{w['key']}" for w in words)
    plain = scan(PLAIN, profiles=[]).json()["screen"]["glossary"]
    assert [w["key"] for w in plain] == ["other"]


# 2026-10-04 (Sushil, on a phone): the sugar card showed "normalization.json added_sugar aliases
# matched: ...". Screen text is for people: no file names, no table keys, no internal ids.
# Fields the PWA uses for logic, classes and links, never as words on the screen
# (tests/test_web.py holds web/app.js to that). `ins` is not one: a card shows "INS " + ins.
MACHINE_FIELDS = {"id", "ref", "key", "url", "kind", "status", "state", "code", "type", "tone",
                  "tier", "concern"}
INTERNAL = re.compile(r"\.json\b|\b[a-z0-9]+_[a-z0-9_]+\b")
SUGARY = ["Sugar", "Invert syrup", "Liquid glucose", "Palm oil", "Hydrogenated vegetable oil",
          "Colour (INS 102)", "Flavour enhancer (INS 621)", "Emulsifier (INS 471)", "Maltodextrin",
          "Milk solids", "Soy lecithin", "Artificial flavouring substances", "Peanut", "Caffeine",
          "Sucralose (INS 955)", "Honey", "Salt"]


def _texts(obj, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _texts(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v, key)
    elif isinstance(obj, str) and key not in MACHINE_FIELDS:
        yield key, obj


def test_screen_text_shows_no_file_names_or_table_keys():
    households = [FAMILY, [{"ref": "me", "age": "adult", "avoid": []},
                           {"ref": "p1", "age": "baby", "avoid": ["milk"]}], None]
    for ingredients in (BISCUIT, PLAIN, MALIBAN, SUGARY):
        for profiles in households:
            s = scan(ingredients, profiles=profiles).json()["screen"]
            leaks = [(k, t) for k, t in _texts(s) if INTERNAL.search(t)]
            assert not leaks, leaks


def test_released_claim_rows_show_no_file_names_or_table_keys(monkeypatch):
    # D-051: claims are shadowed today; this is the check to have before they are released.
    from insidelabel.api import main
    monkeypatch.setattr(main, "CLAIMS_TO_USERS", True)
    claims = ["No preservatives", "No added sugar", "No artificial colours", "100% atta", "No maida",
              "Made with real fruit", "No trans fat", "High protein", "No MSG"]
    ingredients = SUGARY + ["Preservative (INS 202)", "Refined wheat flour (Maida)"]
    r = c.post("/scan", files={"front": ("f.png", PNG, "image/png"), **BACK}, data={
        "replay": vision(ingredients, front_status="read", front_claims=claims,
                         product_match={"status": "match", "evidence": []}),
        "pairing_confirmed": "true", "profiles": json.dumps(FAMILY)})
    s = r.json()["screen"]
    assert s["claims"], "the claim rows were not released"
    leaks = [(k, t) for k, t in _texts(s) if INTERNAL.search(t)]
    assert not leaks, leaks


def test_the_sugar_card_quotes_the_label_and_names_its_source():
    s = scan(SUGARY, profiles=[]).json()["screen"]
    card = next(w for w in s["worth_knowing"] if w["name"].startswith("Sugar under"))
    assert card["label_text"] == "honey, invert syrup, liquid glucose, sugar"
    assert card["technical"] == screen.SUGAR_SOURCE
    industrial = next(w for w in s["worth_knowing"] if w["name"] == "Industrial ingredients")
    assert "NOVA marker" not in industrial["technical"]           # said twice before
    tartrazine = next(w for w in s["worth_knowing"] if "INS 102" in w["technical"])
    assert "Southampton study (Lancet 2007)" in tartrazine["technical"]
    assert "SOUTHAMPTON" not in tartrazine["technical"]


# D-173 follow-up (Sushil, 2026-10-07, "yes"): 50 50 Maska Chaska prints 11 entries and the
# result said "20 ingredients checked", the engine's parsed parts. A list shaped like its own
# (palm and palmolein in one entry, raising agents and emulsifiers grouped by INS number); the
# exact printed list isn't in the repo.
MASKA_CHASKA = ["Refined wheat flour (Maida)", "Edible vegetable oil (Palm, Palmolein)", "Sugar",
                "Invert sugar syrup", "Iodised salt", "Raising agents [503(ii), 500(ii), 341(i)]",
                "Milk solids", "Yeast", "Emulsifiers [322(i), 471]", "Dough conditioner [223]",
                "Flavours (Natural, nature identical and artificial (Butter) flavouring substances)"]


def test_every_ingredient_count_is_the_printed_entries():           # D-111, D-173 follow-up
    from insidelabel.core import engine
    assert engine.analyze(", ".join(MASKA_CHASKA))["ingredient_count_parsed"] > 11   # the old unit
    s = scan(MASKA_CHASKA, profiles=[]).json()["screen"]
    assert s["scope"] == (f"We checked the 11 ingredients on the list against {len(engine._ADDITIVE_BY_INS)} "
                          f"additives and {len(engine.NOVA['markers'])} processing markers in our tables.")
    # The glance ring counts the same 11; "other ingredients look ordinary" is its "other".
    assert s["glance"]["total"] == 11 and sum(s["glance"]["counts"].values()) == 11
    assert s["ordinary"]["count"] == s["glance"]["counts"].get("other", 0) <= 11
    assert s["ordinary"]["text"] == f"{s['ordinary']['count']} other ingredients look ordinary."
    # The sugar chip counts printed entries too ("3rd of 11").
    sugar = next(r for r in s["summary"] if r["key"] == "sugar")
    assert sugar["chip"].endswith("of 11")


def test_a_partly_read_list_says_we_could_read():                # D-173 wording follow-up
    from insidelabel.core import engine
    tail = (f"against {len(engine._ADDITIVE_BY_INS)} additives and {len(engine.NOVA['markers'])} "
            f"processing markers in our tables.")
    s = scan(MASKA_CHASKA, profiles=[], ingredients_status="partial").json()["screen"]
    assert s["scope"] == "We checked the 11 ingredients we could read " + tail
    assert "on the list" not in s["scope"]
    one = scan(["Sugar"], profiles=[], ingredients_status="partial").json()["screen"]
    assert one["scope"] == "We checked the 1 ingredient we could read " + tail
    whole = scan(MASKA_CHASKA, profiles=[]).json()["screen"]
    assert whole["scope"] == "We checked the 11 ingredients on the list " + tail

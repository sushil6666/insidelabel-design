"""
The result screen block (D-060-D-066, D-074). Labels are invented.

What the app renders comes from `screen`; these tests pin the order, the
states that must never appear, and that profile names stay on the device.
"""
import base64
import json

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
    assert people["me"]["line"].startswith("Nothing on your avoid list")


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
    assert s["headline"]["text"] == "Sugar appears under 2 names: liquid glucose, sugar."
    assert s["headline"]["source"]["kind"] == "hidden_sugar"
    # Maltodextrin is added_sugar_adjacent, not a sugar name.
    assert "maltodextrin" not in s["headline"]["text"]
    assert s["band"]["label"] == "Made with industrial ingredients"  # D-063
    assert s["band"]["note"]


def test_nothing_wrong_is_a_designed_state():                       # D-062
    s = scan(PLAIN, profiles=[]).json()["screen"]
    assert s["headline"]["text"] == "No concerns found in the ingredients."
    assert s["checked"] == "We checked the ingredients."            # claims are in shadow
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

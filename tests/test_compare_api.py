"""/compare endpoint (D-057). Labels are invented, not real products."""
from fastapi.testclient import TestClient

from insidelabel.api.main import app
from test_wording import assert_clean, strings

c = TestClient(app)

CREAM = {"id": "a", "name": "Orange Cream Biscuit", "ingredients": [
    "Refined wheat flour (Maida)", "Sugar", "Edible vegetable oil (Palm)", "Invert syrup",
    "Colour (INS 110)", "Emulsifiers (322, 471)", "Raising agent (500(ii))", "Iodised salt"]}
ATTA = {"id": "c", "name": "Whole Wheat Jeera Biscuit", "ingredients": [
    "Whole wheat flour (Atta) 62%", "Edible vegetable oil (Palm)", "Sugar", "Cumin (Jeera) 2%",
    "Raising agent (500(ii))", "Iodised salt"]}
MILKY = {"id": "m", "name": "Milk Rusk", "ingredients": [
    "Whole wheat flour (Atta)", "Milk solids", "Salt"]}


def post(packs, **kw):
    return c.post("/compare", json={"packs": packs, **kw})


def test_best_pick():
    j = post([CREAM, ATTA]).json()
    assert j["outcome"] == "best" and j["best"] == "c"
    assert "No artificial colours" in j["why_best"]
    assert {p["id"] for p in j["packs"]} == {"a", "c"}
    assert_clean(list(strings(j, skip_keys={"technical"})), "/compare")


def test_avoid_list_blocks_pack():
    j = post([ATTA, MILKY], avoid=["milk"], who="Aarav").json()
    assert j["best"] == "c"
    assert j["blocked"] == ["m"]
    assert j["allergen_lines"] == [] and j["who"] == "Aarav"          # D-188: no "not listed" line
    milky = next(p for p in j["packs"] if p["id"] == "m")
    assert milky["allergens"][0]["state"] == "contains"
    assert "Aarav" in milky["allergens"][0]["text"]


def test_unreliable_pack_is_never_best():
    j = post([CREAM, {**ATTA, "reliable": False}]).json()
    assert j["best"] == "a" and j["not_checked"] == ["c"]


def test_low_confidence_with_avoid_list_is_unsure():
    j = post([{**ATTA, "confidence": 0.9}, {**CREAM, "confidence": 0.9}], avoid=["milk"]).json()
    assert j["outcome"] == "no_clear_pick" and j["best"] is None


def test_validation():
    assert post([CREAM]).status_code == 422
    assert post([CREAM, ATTA], age="infant").json()["error"] == "bad_age"   # "baby" is a band since D-140
    assert post([CREAM, {**ATTA, "id": "a"}]).json()["error"] == "duplicate_pack"
    assert post([CREAM, ATTA], avoid=["kryptonite"]).json()["error"] == "unknown_allergen"

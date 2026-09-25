"""Allergen wiring in the API (D-060, D-071, D-072). Labels are invented."""
import base64
import json

from fastapi.testclient import TestClient

from insidelabel.api.main import app

c = TestClient(app)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK_ONLY = {"back": ("back.png", PNG, "image/png")}


def vision(**kw):
    base = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []},
        "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": ["Refined wheat flour (Maida), Sugar, Milk solids, Salt."],
        "ingredient_count": 4,
        "ingredients": ["Refined wheat flour (Maida)", "Sugar", "Milk solids", "Salt"],
        "allergen_statement": "Contains wheat and milk. May contain traces of peanuts.",
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5},
    }
    base.update(kw)
    return json.dumps(base)


def scan(avoid, **kw):
    return c.post("/scan", files=BACK_ONLY, data={"replay": vision(**kw), "avoid": avoid})


def states(j):
    return {r["code"]: r["state"] for r in j["allergens"]["results"]}


def test_allergen_check_endpoint():
    r = c.post("/allergen-check", json={
        "ingredients": ["Wheat flour", "Sugar", "Milk solids"],
        "allergen_statement": "May contain peanuts.",
        "avoid": ["milk", "peanut", "sesame"],
        "who": "Aarav",
    })
    assert r.status_code == 200
    rows = r.json()["allergens"]["results"]
    assert [x["state"] for x in rows] == ["contains", "may_contain", "not_listed"]
    assert "Aarav" in rows[0]["text"]


def test_unknown_code_is_refused():
    r = c.post("/allergen-check", json={"ingredients": ["Sugar"], "avoid": ["kryptonite"]})
    assert r.status_code == 422 and r.json()["error"] == "unknown_allergen"


def test_list_allergens():
    codes = [a["code"] for a in c.get("/allergens").json()["allergens"]]
    assert "milk" in codes and "sesame" in codes


def test_scan_without_avoid_has_null_block():
    r = scan(None)
    assert r.status_code == 200
    assert r.json()["allergens"] is None


def test_scan_allergens_come_first():
    j = scan("milk,peanut").json()
    assert next(iter(j)) == "allergens"
    assert states(j) == {"milk": "contains", "peanut": "may_contain"}


def test_scan_below_095_cannot_confirm():
    j = scan("milk", confidence={"ingredients": 0.9, "front_claims": 0.0, "product_identity": 0.5}).json()
    assert states(j) == {"milk": "cannot_confirm"}


def test_partial_read_cannot_confirm():
    j = scan("milk", ingredients_status="partial").json()
    assert j["verdict"] is not None
    assert states(j) == {"milk": "cannot_confirm"}


def test_refused_scan_still_answers_allergens():
    r = scan("milk", back_status="unreadable")
    assert r.status_code == 422
    assert states(r.json()) == {"milk": "cannot_confirm"}

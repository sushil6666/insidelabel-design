"""
D-198 in the catalogue: a barcode hit checks the reviewed version's list and the veg mark read
when that version was scanned ("on the pack we checked"); a version with no stored mark checks
the list only and says so.
"""
import json
import re

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402
from gtins import gtin  # noqa: E402
from test_pack_kind import reading, st  # noqa: E402
from test_pack_kind_db import env, item_page, post  # noqa: E402, F401

from insidelabel.api import main  # noqa: E402
from insidelabel.lenses import diet  # noqa: E402

ME = json.dumps([{"ref": "me", "age": "adult", "avoid": ["vegetarian", "no_onion_garlic"]}])


def publish(env, ingredients, mark):
    bc = gtin()
    v = reading(ingredients, [st("Sample Jelly", "front")])
    v["product"]["veg_mark"] = mark
    vid = post(bc, v)["catalogue"]["product_version_id"]
    item_id, c, page = item_page(env, vid)
    token = re.search(r'name="csrf" value="([0-9a-f]+)"', page).group(1)
    c.post(f"/review/item/{item_id}/claim", data={"csrf": token})
    r = c.post(f"/review/item/{item_id}/approve", follow_redirects=False, data={
        "csrf": token, "name": "Sample Jelly", "brand": "Testco", "variant": "", "barcode": "",
        "ingredients": "\n".join(ingredients), "allergen_statement": "", "front_claims": "", "note": "",
        "category": "5.1.1"})
    assert r.status_code == 303 and "error=" not in r.headers["location"], r.headers["location"]
    return bc


def hit(bc):
    j = TestClient(main.app).post("/scan", data={"barcode": bc, "profiles": ME}).json()
    assert j["catalogue"]["source"] == "catalogue"
    return j


def test_a_hit_uses_the_stored_brown_mark(env):
    bc = publish(env, ["Sugar", "Water", "Salt"], "non_veg")
    j = hit(bc)
    assert list(j)[:2] == ["allergens", "diet"] and j["diet"]["veg_mark"] == "non_veg"
    assert j["diet"]["mark_from"] == "pack"
    [p] = j["screen"]["people"]
    assert p["line"] == "The pack we checked has the brown non-vegetarian mark."
    assert j["product"]["veg_mark"] == "non_veg"


def test_a_hit_with_no_stored_mark_checks_the_list_only(env):
    bc = publish(env, ["Sugar", "Water", "Salt"], "veg")
    with psycopg.connect(env) as c:
        c.execute("""UPDATE product_versions v SET raw_extraction = raw_extraction #- '{product,veg_mark}'
                      FROM products p WHERE p.id = v.product_id AND p.barcode = %s""", (bc,))
    j = hit(bc)
    assert j["diet"]["veg_mark"] is None and j["screen"]["people"] == []
    [row] = j["screen"]["for_you"]
    assert row["lines"] == [diet.NO_MARK["pack"]]


def test_a_hit_with_gelatin_quotes_the_reviewed_list(env):
    bc = publish(env, ["Sugar", "Gelatine", "Onion Powder"], "veg")
    [p] = hit(bc)["screen"]["people"]
    assert p["status"] == "contains"
    assert p["line"] == "Gelatin is listed: \"Gelatine\"."
    assert p["more"] == ("It comes from animal collagen (skin and bones). "
                         "The pack we checked also has the green vegetarian mark.")
    assert {d["code"]: d["state"] for d in p["diet"]} == {"vegetarian": "contains", "no_onion_garlic": "contains"}

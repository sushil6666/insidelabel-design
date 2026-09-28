"""
D-120: "candy sugar syrup" and "sugar syrup" are added sugars (FSS Labelling and
Display Regulations 2020: added sugars are mono- and disaccharides added to
food); bare "malt", a malted grain, is not. Found on Lotus Biscoff in the shop
(2026-09-27), which read "No concerns found" with sugar under two names.
"""
import json

from fastapi.testclient import TestClient

from insidelabel.api import main
from insidelabel.core import engine
from insidelabel.extraction.providers import cloud_vision

BISCOFF = ["Refined Wheat Flour (Maida)", "Sugar", "Edible Vegetable Oils (Palm, Sunflower, Palm Stearin)",
           "Candy Sugar Syrup", "Raising Agent (Sodium Bicarbonate)", "Soy Flour", "Iodised Salt",
           "Cinnamon Powder"]


def test_candy_sugar_syrup_and_sugar_syrup_are_added_sugars():
    assert engine.analyze(", ".join(BISCOFF))["hidden_sugar_names"] == ["candy sugar syrup", "sugar"]
    assert engine.analyze("Wheat Flour, Sugar Syrup, Salt")["hidden_sugar_names"] == ["sugar syrup"]


def test_bare_malt_is_not_a_sugar_name():
    # The sugar-free masala cracker: MALT is malted grain; "malt extract" stays a sugar.
    assert engine.analyze("Wheat Flour, Yeast, Malt, Salt")["hidden_sugar_names"] == []
    assert engine.analyze("Wheat Flour, Malt Extract, Salt")["hidden_sugar_names"] == ["malt extract"]


def test_biscoff_headline_names_both_sugars():
    vision = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Lotus", "name": "Biscoff", "variant": None, "net_quantity": None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(BISCOFF)], "ingredient_count": len(BISCOFF), "ingredients": BISCOFF,
        "allergen_statement": "Contains wheat, soy.", "front_claims": [], "front_claim_footnotes": [],
        "extraction_notes": [], "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.8}}
    photo = b"\xff\xd8\xff\xe0biscoff-back"
    text = {cloud_vision.digest(photo): "INGREDIENTS: " + ", ".join(BISCOFF) + ". CONTAINS WHEAT, SOY."}
    with cloud_vision.replaying(text):
        r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                      data={"replay": json.dumps(vision)})
    assert r.status_code == 200, r.text
    # D-123: where sugar sits, then its other name.
    assert r.json()["screen"]["headline"]["text"] == \
        "Sugar is the 2nd ingredient, and appears again as candy sugar syrup."

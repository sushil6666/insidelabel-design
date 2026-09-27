"""
D-115: a processing marker is shown in the pack's words, never in our table's.

The first real scan on the live site (an Organic India Tulsi Mulethi pack,
2026-09-27) showed "such as added flavour (natural/artificial/nature-identical)"
and quoted it as "On the label": the name of our table row, which put
"artificial" next to a brand whose pack may only say "natural flavour" (D-042,
D-071). These pin that the headline and the quote use words from the label,
while which row matches (and so the verdict) is unchanged. Labels are invented.
"""
import base64
import json
import re

import pytest
from fastapi.testclient import TestClient

from insidelabel.api.main import app
from insidelabel.core import classify, engine

c = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
MARKERS = engine.NOVA["markers"]


def screen_for(ingredients):
    v = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": None,
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5},
    }
    r = c.post("/scan", files={"back": ("b.png", PNG, "image/png")}, data={"replay": json.dumps(v)})
    assert r.status_code == 200, r.text
    return r.json()["screen"]


def nova_item(s):
    return next((w for w in s["worth_knowing"] if w["source"]["kind"] == "nova"), None)


def words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def test_tulsi_mulethi_quotes_natural_flavour():
    s = screen_for(["Tulsi", "Mulethi", "Natural flavour"])
    assert s["headline"]["text"] == "Made with industrial ingredients, such as natural flavour."
    item = nova_item(s)
    assert item["label_text"] == "natural flavour"
    assert "artificial" not in s["headline"]["text"] + item["label_text"]
    # The table row is still named, as a reference, in the technical line.
    assert "Added flavour (natural/artificial/nature-identical)" in item["technical"]


@pytest.mark.parametrize("ingredient, shown, never", [
    ("Natural flavour", "natural flavour", {"artificial", "identical"}),
    ("Hydrogenated vegetable oil", "hydrogenated vegetable oil", {"interesterified"}),
    ("Thickener (INS 415)", "thickener", {"cosmetic", "stabiliser", "humectant"}),
    ("Whey protein isolate", "whey protein isolate", {"additive"}),
    ("Anti-caking agent (INS 551)", "anti-caking agent", {"bulking", "glazing"}),
    ("Artificial flavouring substances (Vanilla)", "artificial flavouring substances", set()),
])
def test_the_six_rows_show_only_what_the_label_says(ingredient, shown, never):
    s = screen_for(["Sugar", ingredient])
    item = nova_item(s)
    assert item is not None, "the marker must still match (D-115 changes words only)"
    assert item["label_text"] == shown
    assert not never & words(item["label_text"])
    if s["headline"]["source"]["kind"] == "nova":
        assert not never & words(s["headline"]["text"])


@pytest.mark.parametrize("marker, alias", [(m, al) for m in MARKERS for al in m["aliases"]],
                         ids=lambda x: x if isinstance(x, str) else x["id"])
def test_every_known_name_is_shown_in_the_labels_own_words(marker, alias):
    label = ["Water", alias.capitalize()]
    s = screen_for(label)
    item = nova_item(s)
    if item is None:
        pytest.skip("matched as an additive or a sugar first, not as a marker")
    assert words(item["label_text"]) <= words(", ".join(label)), item["label_text"]
    if s["headline"]["source"]["kind"] == "nova":
        shown = s["headline"]["text"].removeprefix("Made with industrial ingredients, such as ")
        assert words(shown) <= words(", ".join(label)), s["headline"]["text"]


def test_a_fragment_shows_the_rows_longest_known_name_inside_it():
    flavour = next(m for m in MARKERS if m["id"] == "nova_flavour")
    assert classify._label_term("flavours (natural", flavour) == "flavour"
    assert classify._label_term("natural flavour (vanilla", flavour) == "natural flavour"
    assert classify._label_term("natural flavour", flavour) == "natural flavour"


def test_which_row_matches_is_unchanged():
    r = engine.analyze("Sugar, Natural flavour, Thickener (INS 415)")
    rows = sorted(f["matched_as"] for f in r["flags"] if f["type"] == "nova_marker")
    assert rows == ["NOVA marker: Added flavour (natural/artificial/nature-identical)",
                    "NOVA marker: Stabiliser / thickener / humectant (cosmetic use)"]
    assert r["nova_ultra_processed"] is True

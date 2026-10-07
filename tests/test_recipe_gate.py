"""
D-166: a recipe printed on the pack, read as if it were the pack's ingredient list,
is refused as "no ingredient list found", with retake words that say a recipe was
read. A rule decides (D-004): the markers are data/recipe_markers.json.

The case: Saffola Soya Chunks (8901088072236), 2026-10-06. The back photo was the
cooking side, whose "SOYA MASALA GRAVY RECIPE" box has its own "INGREDIENTS:"
heading. That scan read the pack from a second photo, so it reached no user; a scan
with the recipe photo alone could have shown "Curd" (milk) and "Cashews" (tree nut)
as the pack's contents.
"""
import glob
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from test_checker_stamps_and_cuts import GEMINI

from insidelabel.api import main
from insidelabel.extraction.providers import prompt
from insidelabel.lenses import screen
from insidelabel.reliability import gates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The recipe box, split at its top-level commas as the model returns a list (prompt rule 4).
SAFFOLA_RECIPE = (
    "2 cups cooked Saffola Soya Chunks, 3 tsp Oil, 1 tsp Cumin seeds, 1 Bay leaf, 1/2 tsp Turmeric powder, "
    "1-inch Cinnamon stick, 1 Onion, finely chopped, Salt to taste, 1 tsp Kashmiri chilli powder, 2 tsp Oil, "
    "1 tsp Coriander powder, 1/4 cup Curd, fresh, 1 cup Water, 1 tsp Kasuri methi, crushed, "
    "1/4 tsp Garam masala, 1 Onion, thinly sliced, 3 cloves Garlic, 1 inch Ginger, 2 Tomatoes, finely chopped, "
    "8 Cashews, whole (Optional)").split(", ")
CAKE = json.load(open(os.path.join(ROOT, "gold", "ziggy-donut-cake-choco-vanilla.json"), encoding="utf-8"))


def reading(ingredients):
    return {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
            "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
            "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
            "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
            "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
            "ingredients": ingredients, "allergen_statement": None, "front_claims": [],
            "front_claim_footnotes": [], "extraction_notes": [],
            "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}


def test_the_saffola_recipe_is_refused_as_no_ingredient_list():
    assert len(gates.recipe_entries(SAFFOLA_RECIPE)) == 21 and len(SAFFOLA_RECIPE) == 26
    proceed, rel = gates.assess(reading(SAFFOLA_RECIPE))
    assert proceed is False
    assert rel["error"] == "no_ingredient_list_found" and rel["reason"] == "recipe"
    assert "21 of 26" in rel["detail"]


@pytest.mark.parametrize("ingredients", [
    GEMINI,                                                          # report #5's wafer list
    CAKE["ingredients"],                                             # the Choco Vanilla cake
    ["Defatted Soya"],                                               # Saffola's own list
    ["Cup cake mix", "Sugar"],
    ["Wheat flour", "Chopped nuts (Cashew 5%)", "Sugar"],
    ["Salt"],
    ["Tomato paste (28%)", "Water", "Salt"],
    ["Fresh cream", "Sugar", "Raising agent (500(ii))"],
    ["Wheat flour", "Sugar", "1 tsp Baking soda", "Salt", "Milk solids"],   # one stray measure
])
def test_real_lists_pass(ingredients):
    proceed, rel = gates.assess(reading(ingredients))
    assert proceed is True and rel["error"] is None, gates.recipe_entries(ingredients)


def _lists(obj):
    if isinstance(obj, dict):
        got = obj.get("ingredients")
        if isinstance(got, list) and got and all(isinstance(x, str) for x in got):
            yield got
        for v in obj.values():
            yield from _lists(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _lists(v)


def test_no_list_we_have_read_is_taken_for_a_recipe():
    # One test, not one per file, so the count is the same with or without predictions/
    # (the laptop's gold predictions; gitignored, so absent in a cloud checkout).
    seen = {}
    for pattern in ("gold/*.json", "predictions/*.json", "predictions_archive/*.json", "tests/fixtures/**/*.json"):
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            for ingredients in _lists(json.load(open(path, encoding="utf-8"))):
                seen[path] = seen.get(path, 0) + 1
                assert not gates.is_recipe(ingredients), (path, gates.recipe_entries(ingredients))
    assert sum(1 for p in seen if "/gold/" in p) == 6
    assert sum(1 for p in seen if "/predictions_archive/" in p) == 8     # limca.json is an error answer


def test_the_retake_says_a_recipe_was_read():
    r = TestClient(main.app).post("/scan", files={"back": ("b.jpg", b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes,
                                                           "image/jpeg")},
                                  data={"replay": json.dumps(reading(SAFFOLA_RECIPE))})
    assert r.status_code == 422, r.text
    s = r.json()["screen"]
    assert r.json()["reliability"]["error"] == "no_ingredient_list_found"
    assert s["state"] == "retake" and s["retake"] == screen.RETAKE_RECIPE
    assert s["headline"]["text"] == screen.HEADLINE.get("no_ingredient_list_found", s["headline"]["text"])


def test_the_prompt_says_a_recipe_is_not_the_list():
    assert "a recipe printed on the pack" in prompt.VISION_PROMPT
    assert 'belongs to a recipe, set ingredients_status to "not_found"' in prompt.VISION_PROMPT


# ---------------------------------------------------------------- D-092: stored and replayed

psycopg = pytest.importorskip("psycopg")


@pytest.fixture(scope="module")
def env(fresh_db, tmp_path_factory):
    from insidelabel.db.store import Store
    from insidelabel.media import LocalMedia
    saved = (main.STORE, main.MEDIA)
    main.STORE = Store(fresh_db[0])
    main.MEDIA = LocalMedia(str(tmp_path_factory.mktemp("media")))
    yield fresh_db[0]
    main.STORE, main.MEDIA = saved


def test_a_refused_recipe_scan_is_stored_and_replays_the_same(env):
    from gtins import gtin

    from insidelabel import repro
    photo = b"\xff\xd8\xff\xe0" + uuid.uuid4().bytes
    first = TestClient(main.app).post("/scan", files={"back": ("b.jpg", photo, "image/jpeg")},
                                      data={"replay": json.dumps(reading(SAFFOLA_RECIPE)), "barcode": gtin()})
    assert first.status_code == 422, first.text
    with psycopg.connect(env) as c:
        cur = c.execute("SELECT * FROM scans WHERE id = %s", (first.json()["scan_id"],))
        row = dict(zip([d.name for d in cur.description], cur.fetchone()))
    assert (row["outcome"], row["error_code"]) == ("refused", "no_ingredient_list_found")
    assert row["model_raw"]                                           # the model's answer is kept
    out = repro.replay_scan(row, media=main.MEDIA)
    assert out["status"] == 422
    assert out["body"]["reliability"]["error"] == "no_ingredient_list_found"
    assert out["screen"]["retake"] == first.json()["screen"]["retake"] == screen.RETAKE_RECIPE

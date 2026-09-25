"""India vs EU vs US comparison (D-086): optional, information only, FSSAI decides the verdict."""
import json
import os

from fastapi.testclient import TestClient

from insidelabel.api.main import app
from insidelabel.core import engine
from insidelabel.lenses import regulators
from test_wording import assert_clean, strings

c = TestClient(app)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LABEL = ("Sugar, Liquid glucose, Gelatin, Colours (INS 171, INS 122, INS 127, INS 102), "
         "Acidity regulator (INS 330), Emulsifier (INS 322)")


def test_off_by_default():
    j = c.post("/analyze", json={"raw_ingredients": LABEL}).json()
    assert j["regulators"] is None


def test_never_changes_the_verdict():
    plain = c.post("/analyze", json={"raw_ingredients": LABEL}).json()
    compared = c.post("/analyze", json={"raw_ingredients": LABEL, "compare_regulators": True}).json()
    assert plain["verdict"] == compared["verdict"]


def test_comparison_content():
    reg = c.post("/analyze", json={"raw_ingredients": LABEL, "compare_regulators": True}).json()["regulators"]
    assert reg["basis"].startswith("The result above uses Indian (FSSAI) rules only")
    rows = {r["ins"]: r for r in reg["additives"]}
    tio2 = rows["171"]["regulators"]
    assert tio2["IN"]["status"] == "permitted_gmp"
    assert tio2["EU"]["status"] == "not_permitted_since" and "7 August 2022" in tio2["EU"]["text"]
    assert tio2["US"]["status"] == "permitted_max"
    assert rows["122"]["regulators"]["US"]["status"] == "not_permitted"
    assert rows["127"]["regulators"]["US"]["status"] == "revoked"
    # differs first; tartrazine is allowed everywhere (EU with a warning)
    assert rows["102"]["differs"] is False
    assert [r["differs"] for r in reg["additives"]] == sorted(
        [r["differs"] for r in reg["additives"]], reverse=True)
    # found by the engine but not compared yet: listed, not guessed
    assert "330" in reg["not_yet_compared"] and "322" in reg["not_yet_compared"]


def test_india_listed_first():
    r = regulators.row("171")
    assert list(r["regulators"]) == ["IN", "EU", "US"]


def test_unchecked_jurisdiction_is_said_not_guessed():
    us = regulators.row("952")["regulators"]["US"]
    assert us["status"] == "not_checked" and us["source"] is None


def test_every_row_has_source_and_date():
    with open(os.path.join(ROOT, "data", "regulatory_status.json"), encoding="utf-8") as f:
        t = json.load(f)
    statuses = t["_meta"]["status_text"]
    for r in t["additives"]:
        assert r.get("verified_on"), r["ins"]
        assert "IN" in r, f"{r['ins']}: India is the basis and must always be checked"
        for j in ("IN", "EU", "US"):
            if j in r:
                assert r[j]["status"] in statuses, (r["ins"], j)
                assert r[j]["doc"] in t["_meta"]["documents"], (r["ins"], j)
                regulators._text(r[j])          # every template placeholder is filled


def test_every_compared_additive_is_known_to_engine():
    for ins in regulators.ROWS:
        assert ins in engine._ADDITIVE_BY_INS, f"INS {ins} compared but the engine can't detect it"


def test_scores_use_fssai_only():
    """No concern level or flag may rest on another country's legal status."""
    for a in engine.ADDITIVES["additives"]:
        assert not any(f.startswith("banned_") for f in a["flags"]), a["ins"]
        assert "banned" not in a["why"].lower(), a["ins"]


def test_wording():
    rows = [regulators.row(i) for i in regulators.ROWS]
    assert_clean(list(strings(rows, skip_keys={"title", "url"})), "regulators")
    assert_clean([regulators.BASIS], "regulators basis")


def test_lookup_endpoints():
    assert c.get("/regulators/171").json()["name"] == "Titanium dioxide"
    assert c.get("/regulators/330").status_code == 404
    assert c.get("/regulators").json()["additives"][0]["differs"] is True


def test_scan_option():
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    vision = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [LABEL], "ingredient_count": 6,
        "ingredients": ["Sugar", "Liquid glucose", "Gelatin", "Colours (INS 171, INS 122, INS 127, INS 102)",
                        "Acidity regulator (INS 330)", "Emulsifier (INS 322)"],
        "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5},
    }
    files = {"back": ("b.png", png, "image/png")}
    off = c.post("/scan", files=files, data={"replay": json.dumps(vision)}).json()
    on = c.post("/scan", files=files, data={"replay": json.dumps(vision), "compare_regulators": "true"}).json()
    assert off["regulators"] is None
    assert on["regulators"]["differs_count"] >= 3
    assert off["verdict"] == on["verdict"]

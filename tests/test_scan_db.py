"""
/scan and /report with the database on (D-024, D-026, D-028, D-043, D-073, D-076).

Vision calls are replayed from recorded JSON, so nothing here spends money.
"""
import base64
import json
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from gtins import gtin  # noqa: E402
from insidelabel.api import main  # noqa: E402
from insidelabel.db.store import Store, build_findings, ingredients_hash  # noqa: E402
from insidelabel.core import engine  # noqa: E402
from insidelabel.claims import checker  # noqa: E402

c = TestClient(main.app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BACK = {"back": ("b.png", PNG, "image/png")}
BOTH = {"back": ("b.png", PNG, "image/png"), "front": ("f.png", PNG, "image/png")}

V1 = ["Refined wheat flour (Maida)", "Sugar", "Invert syrup", "Milk solids",
      "Preservative (INS 211)", "Emulsifier (INS 322)"]
V2 = ["Refined wheat flour (Maida)", "Sugar", "Invert syrup", "Milk solids",
      "Emulsifier (INS 322)"]                      # reformulated: preservative gone


def vision(ingredients, **kw):
    v = {
        "front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
        "product": {"brand": "Testco", "name": "Cream Biscuit", "variant": None,
                    "net_quantity": "100 g", "veg_mark": "veg"},
        "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
        "back_identity": {"brand": "Testco", "name": None, "manufacturer": None, "fssai_licence": None},
        "ingredient_lines": [", ".join(ingredients)], "ingredient_count": len(ingredients),
        "ingredients": ingredients, "allergen_statement": "Contains wheat, milk.",
        "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
        "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.9},
    }
    v.update(kw)
    return json.dumps(v)


@pytest.fixture(scope="module")
def db(fresh_db):
    uri = fresh_db[0]
    old = main.STORE
    main.STORE = Store(uri)
    yield uri
    main.STORE = old


def q(uri, sql, *args):
    with psycopg.connect(uri) as conn:
        return conn.execute(sql, args).fetchall()


def scan(files=BACK, **data):
    if data.get("replay"):
        data.setdefault("barcode", gtin())   # D-107: only barcoded packs are catalogued
    return c.post("/scan", files=files, data=data)


# ---------------------------------------------------------------- pure

def test_every_finding_has_evidence_pointing_at_the_label():
    raw = ", ".join(V1)
    v = engine.analyze(raw)
    cc = checker.check_claims(["No preservatives"], raw, v)
    fs = build_findings(V1, v, cc, "0.1")
    assert fs and all(f["evidence"] for f in fs)
    ins211 = next(f for f in fs if f["rule_code"] == "ADDITIVE:INS 211")
    assert ins211["evidence"][0]["pointer"] == {"ingredient_position": 5}
    claim = next(f for f in fs if f["rule_code"] == "CLAIM:no_preservatives")
    assert claim["tier"] == "R2" and claim["rendered_text"].startswith('The label claims "No preservatives".')
    assert {e["kind"] for e in claim["evidence"]} == {"claim", "ingredient"}


def test_hash_ignores_case_and_spacing_not_order():
    assert ingredients_hash(["Sugar", "Salt"]) == ingredients_hash(["  sugar ", "SALT"])
    assert ingredients_hash(["Sugar", "Salt"]) != ingredients_hash(["Salt", "Sugar"])


# ---------------------------------------------------------------- flow

def test_full_barcode_lifecycle(db):
    bc = "8901234567890"
    dev = str(uuid.uuid4())

    # 1. Barcode alone, unknown pack: ask for a photo. Nothing stored.
    r = scan(files={}, barcode=bc)
    assert r.status_code == 404 and r.json()["error"] == "not_in_catalogue"

    # 2. Photo + barcode: vision path, stored as a version waiting for review.
    j = scan(replay=vision(V1), barcode=bc, device_id=dev).json()
    assert next(iter(j)) == "allergens"
    assert j["catalogue"]["status"] == "pending_review" and j["catalogue"]["queued_for_review"] == "new_product"
    vid = j["catalogue"]["product_version_id"]
    row = q(db, "SELECT status, is_current, model_name, prompt_version, engine_version "
                "FROM product_versions WHERE id = %s", vid)[0]
    assert row[:2] == ("pending_review", False)
    assert row[2] == main.MODEL and row[3] == main.PROMPT_VERSION and row[4] == main.ENGINE_VERSION

    # findings stored, each with evidence (the DB trigger would refuse otherwise)
    nf = q(db, "SELECT count(*) FROM findings WHERE product_version_id = %s", vid)[0][0]
    assert nf == len(j["verdict"]["flags"])
    assert q(db, """SELECT count(*) FROM findings f WHERE product_version_id = %s AND NOT EXISTS
                    (SELECT 1 FROM finding_evidence fe WHERE fe.finding_id = f.id)""", vid)[0][0] == 0

    # 3. Same pack scanned again before review: same version, not queued twice.
    j2 = scan(replay=vision(V1), barcode=bc).json()
    assert j2["catalogue"]["product_version_id"] == vid and j2["catalogue"]["queued_for_review"] is None
    assert q(db, "SELECT count(*) FROM review_queue WHERE product_version_id = %s", vid)[0][0] == 1

    # 4. Still unpublished, so barcode-only still can't serve it (D-028).
    assert scan(files={}, barcode=bc).status_code == 404

    # 5. A reviewer publishes it.
    q_pub(db, vid)

    # 6. Barcode alone now answers from the catalogue: no photo, no vision call.
    k = scan(files={}, barcode=bc, avoid="milk", device_id=dev).json()
    assert next(iter(k)) == "allergens"
    assert k["catalogue"]["source"] == "catalogue" and k["catalogue"]["last_verified"]
    assert k["catalogue"]["allergen_recheck_suggested"] is True          # D-073
    kp = scan(files={}, barcode=bc, device_id=dev,
              profiles=json.dumps([{"ref": "p1", "age": "kid", "avoid": ["milk"]}])).json()
    assert kp["screen"]["last_verified"].startswith("Label last verified on")
    assert kp["screen"]["recheck"] and kp["screen"]["people"][0]["status"] == "contains"
    assert k["allergens"]["results"][0]["state"] == "contains"
    assert k["verdict"] == j["verdict"]
    assert q(db, "SELECT cache_hit, ai_cost_paise FROM scans WHERE id = %s", k["scan_id"])[0] == (True, 0)

    # 7. Re-check photo shows the same label: nothing new to review.
    j3 = scan(replay=vision(V1), barcode=bc).json()
    assert j3["catalogue"]["status"] == "published" and j3["catalogue"]["queued_for_review"] is None

    # 8. The pack was reformulated under the same barcode.
    j4 = scan(replay=vision(V2), barcode=bc).json()
    assert j4["catalogue"]["queued_for_review"] == "reformulation"
    assert j4["catalogue"]["product_version_id"] != vid
    # the old version keeps serving until a reviewer publishes the new one
    assert scan(files={}, barcode=bc).json()["catalogue"]["product_version_id"] == vid

    # 7 scans of this barcode, including the profiles scan after step 6.
    assert q(db, "SELECT scan_count FROM products WHERE barcode = %s", bc)[0][0] == 7


def q_pub(uri, vid):
    with psycopg.connect(uri) as conn:
        conn.execute("SELECT publish_version(%s, 'reviewer')", (vid,))


def test_claims_only_stored_when_pairing_is_trusted(db):
    claims = ["No preservatives"]
    # front read but pairing not confirmed -> claims must not be stored
    j = scan(files=BOTH, replay=vision(V1, front_status="read", front_claims=claims,
                                       product_match={"status": "indeterminate", "evidence": []})).json()
    vid = j["catalogue"]["product_version_id"]
    stored = q(db, "SELECT front_claims FROM product_versions WHERE id = %s", vid)[0][0]
    assert stored == []
    assert q(db, "SELECT count(*) FROM findings WHERE product_version_id = %s AND rule_code LIKE 'CLAIM:%%'",
             vid)[0][0] == 0


def test_claim_check_is_shadowed_until_released(db, monkeypatch):
    # D-051: computed and stored for reviewers, shown to users only when switched on.
    claims = ["No preservatives"]
    ing = ["Wheat flour", "Sugar", "Preservative (INS 202)"]      # unique: a fresh version
    data = dict(files=BOTH, pairing_confirmed="true",
                replay=vision(ing, front_status="read", front_claims=claims,
                              product_match={"status": "indeterminate", "evidence": []}))
    monkeypatch.setattr(main, "CLAIMS_TO_USERS", False)
    j = scan(**data).json()
    assert j["claim_check"]["status"] == "not_checked"
    assert j["claim_check"]["reason"] == "claims_not_released"
    assert j["claim_check"]["checked"] == []
    vid = j["catalogue"]["product_version_id"]
    assert q(db, "SELECT count(*) FROM findings WHERE product_version_id = %s "
                 "AND rule_code = 'CLAIM:no_preservatives'", vid)[0][0] == 1

    monkeypatch.setattr(main, "CLAIMS_TO_USERS", True)
    j = scan(**data).json()
    assert j["claim_check"]["status"] == "checked"
    assert any(ch["contradicted"] for ch in j["claim_check"]["checked"])


def test_refused_scan_is_recorded(db):
    r = scan(replay=vision(V1, back_status="unreadable"))
    assert r.status_code == 422
    sid = r.json()["scan_id"]
    assert q(db, "SELECT outcome, error_code, product_version_id FROM scans WHERE id = %s", sid)[0] == \
        ("refused", "back_not_read", None)


def test_bad_barcode_rejected(db):
    assert scan(files={}, barcode="12345").json()["error"] == "bad_barcode"


def test_report_a_mistake(db):
    sid = scan(replay=vision(["Rice flour", "Salt"])).json()["scan_id"]
    r = c.post("/report", json={"scan_id": sid, "field": "ingredients",
                                "proposed_value": "Rice flour, Salt, Sesame", "note": "missed sesame"})
    assert r.status_code == 200
    rid = r.json()["review_id"]
    assert q(db, "SELECT kind, status FROM review_queue WHERE id = %s", rid)[0] == ("correction", "open")
    assert c.post("/report", json={"scan_id": str(uuid.uuid4()), "field": "x",
                                   "note": "misread"}).status_code == 404
    r = c.post("/report", json={"field": "x", "note": "misread"})
    assert r.status_code == 422 and r.json()["error"] == "no_subject"


def test_empty_report_refused_before_anything_is_stored(db):
    """D-109: a report needs what the pack says or a note; the field alone isn't enough."""
    sid = scan(replay=vision(["Rice flour", "Salt"])).json()["scan_id"]
    before = q(db, "SELECT count(*) FROM review_queue")[0][0]
    for body in ({}, {"note": None, "proposed_value": None}, {"note": "   ", "proposed_value": "\n"},
                 {"note": "ok"}, {"proposed_value": " . "}):
        r = c.post("/report", json={"scan_id": sid, "field": "other", **body})
        assert r.status_code == 422, body
        assert (r.json()["error"], r.json()["detail"]) == ("empty_report", main.EMPTY_REPORT)
    assert q(db, "SELECT count(*) FROM review_queue")[0][0] == before
    # An empty report about a scan that doesn't exist is still refused as empty, not 404.
    r = c.post("/report", json={"scan_id": str(uuid.uuid4()), "field": "other"})
    assert r.json()["error"] == "empty_report"


def test_one_box_filled_is_enough(db):
    """D-109: either box on its own, with real text, sends the report."""
    sid = scan(replay=vision(["Rice flour", "Salt"])).json()["scan_id"]
    assert c.post("/report", json={"scan_id": sid, "field": "other", "note": "  Has sesame  "}).status_code == 200
    assert c.post("/report", json={"scan_id": sid, "field": "ingredients",
                                   "proposed_value": "Rice flour, Salt, Sesame"}).status_code == 200


def test_db_failure_never_costs_the_user_their_result(db, monkeypatch):
    def boom(**_kw):
        raise psycopg.OperationalError("database down")
    monkeypatch.setattr(main.STORE, "save_scan", boom)
    j = scan(replay=vision(V1)).json()
    assert j["verdict"] is not None and j["scan_id"] is None

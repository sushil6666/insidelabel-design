"""Marketplace leads and provenance (D-088, D-089): a listing is a lead, the pack is the record."""
import json
import os
import sys

import pytest

psycopg = pytest.importorskip("psycopg")

from insidelabel.core import engine  # noqa: E402
from insidelabel.db.leads import LeadError, Leads, store_screenshot  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import leads as leads_cli  # noqa: E402

ING = ["Carbonated water", "Sugar", "Acidity regulator (INS 330)", "Preservative (INS 211)"]


def vision(ingredients):
    return {"product": {"brand": "Leadco", "name": "Lemon Drink"}, "ingredients": ingredients,
            "ingredient_lines": [", ".join(ingredients)], "allergen_statement": None,
            "front_claims": [], "confidence": {"ingredients": 0.98}}


def scan(uri, barcode, ingredients=ING):
    v = engine.analyze(", ".join(ingredients))
    return Store(uri).save_scan(vision=vision(ingredients), verdict=v, claim_check=None,
                                claims_trusted=False, reliability={}, barcode=barcode,
                                engine_version="test")


def q(uri, sql, *args):
    with psycopg.connect(uri) as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else None


@pytest.fixture(scope="module")
def db(fresh_db):
    return fresh_db[0]


def test_full_lead_lifecycle(db):
    L = Leads(db)
    lead = L.add(product="Lemon Drink", brand="Leadco", net_quantity="750 ml",
                 source_platform="Flipkart", source_url="https://example.invalid/p/1", noted_by="t")
    assert lead["evidence_status"] == "needs_primary_source"
    assert lead["production_source"] == "physical_label"
    assert lead["source_type"] == "marketplace_reference"

    assert L.pack_obtained(lead["id"])["evidence_status"] == "pack_obtained"
    s = scan(db, "8900000000012")
    linked = L.link(lead["id"], barcode="8900000000012")
    assert linked["evidence_status"] == "label_captured"
    assert linked["product_version_id"] == s["product_version_id"]

    # Publishing the version (what /review does) closes the lead in the database.
    q(db, "SELECT publish_version(%s, 'reviewer')", s["product_version_id"])
    assert L.get(lead["id"])["evidence_status"] == "published"


def test_linking_to_an_already_published_version_closes_the_lead(db):
    L = Leads(db)
    s = scan(db, "8900000000029")
    q(db, "SELECT publish_version(%s, 'reviewer')", s["product_version_id"])
    lead = L.add(product="Lemon Drink", source_platform="Zepto", noted_by="t")
    assert L.link(lead["id"], product_version_id=s["product_version_id"])["evidence_status"] == "published"


def test_a_listing_version_can_never_be_published(db):
    s = scan(db, "8900000000036")
    vid = s["product_version_id"]
    q(db, "UPDATE product_versions SET production_source = 'marketplace_listing' WHERE id = %s", vid)
    with pytest.raises(psycopg.errors.CheckViolation):
        q(db, "SELECT publish_version(%s, 'reviewer')", vid)


def test_a_lead_cannot_be_closed_by_a_listing_version(db):
    L = Leads(db)
    s = scan(db, "8900000000043", ING[:3])
    vid = s["product_version_id"]
    q(db, "UPDATE product_versions SET production_source = 'marketplace_listing' WHERE id = %s", vid)
    lead = L.add(product="Lemon Drink", source_platform="Blinkit", noted_by="t")
    with pytest.raises(LeadError, match="physical label"):
        L.link(lead["id"], product_version_id=vid)
    # …and the database refuses it even if the code is bypassed.
    with pytest.raises(psycopg.errors.RaiseException):
        q(db, """UPDATE product_leads SET evidence_status = 'label_captured', product_version_id = %s
                  WHERE id = %s""", vid, lead["id"])


def test_status_rules(db):
    L = Leads(db)
    lead = L.add(product="Namkeen", source_platform="Swiggy Instamart", noted_by="t")
    with pytest.raises(LeadError):
        L.abandon(lead["id"], "  ")                                   # a reason is required
    with pytest.raises(LeadError, match="scan the pack first"):
        L.link(lead["id"], barcode="0000000000000")
    with pytest.raises(psycopg.errors.CheckViolation):                # published needs a version
        q(db, "UPDATE product_leads SET evidence_status = 'published' WHERE id = %s", lead["id"])
    gone = L.abandon(lead["id"], "not sold offline")
    assert gone["evidence_status"] == "abandoned" and gone["status_note"] == "not sold offline"
    with pytest.raises(LeadError):
        L.pack_obtained(lead["id"])                                    # abandoned is final
    with pytest.raises(LeadError, match="platform"):
        L.add(product="X", source_platform="Myntra", noted_by="t")


def test_duplicate_barcode_and_screenshot_are_refused(db, tmp_path):
    L = Leads(db)
    L.add(product="Chips", barcode="8900000000050", source_platform="Amazon", noted_by="t")
    with pytest.raises(LeadError, match="already lead"):
        L.add(product="Chips", barcode="8900000000050", source_platform="Zepto", noted_by="t")

    shot = tmp_path / "s.png"
    shot.write_bytes(b"not really a png")
    digest = store_screenshot(str(shot), str(tmp_path / "research"))
    assert (tmp_path / "research" / "screenshots" / f"{digest}.png").exists()
    L.add(product="Chips 2", screenshot_sha256=digest, noted_by="t")
    with pytest.raises(LeadError, match="already lead"):
        L.add(product="Chips 2 again", screenshot_sha256=digest, noted_by="t")


def test_review_refuses_a_listing_version(db):
    from insidelabel.review.service import ReviewError, ReviewService
    s = scan(db, "8900000000067", ING[:2])
    vid = s["product_version_id"]
    q(db, "UPDATE product_versions SET production_source = 'marketplace_listing' WHERE id = %s", vid)
    rid = q(db, "SELECT id FROM review_queue WHERE product_version_id = %s", vid)[0][0]
    svc = ReviewService(db, "test")
    svc.claim(rid, "rev")
    with pytest.raises(ReviewError, match="online listing"):
        svc.approve(rid, "rev", {"name": "Lemon Drink", "category": "14.1.4.1",
                                  "ingredients": "\n".join(ING[:2])})


def test_cli_export_matches_the_provenance_shape(db, capsys):
    leads_cli.main(["--db", db, "add", "Limca", "--brand", "Coca-Cola", "--platform", "Flipkart"])
    capsys.readouterr()
    leads_cli.main(["--db", db, "export"])
    rec = [r for r in json.loads(capsys.readouterr().out) if r["product"] == "Limca"][0]
    assert {k: rec[k] for k in ("product", "source_type", "source_platform",
                                "production_source", "evidence_status")} == {
        "product": "Limca", "source_type": "marketplace_reference", "source_platform": "Flipkart",
        "production_source": "physical_label", "evidence_status": "needs_primary_source"}


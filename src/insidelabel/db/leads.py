"""
Product leads: marketplace listings used as research, never as the record (D-088, D-089).

The flow for every product that enters the catalogue this way:

    listing screenshot ─► lead (needs_primary_source)
                          │  buy / find the actual pack
                          ▼
                          pack_obtained
                          │  photograph front + back, scan it (/scan or batch_scan)
                          ▼
                          label_captured  ── linked to the physical-label version
                          │  reviewer checks it against the photos (/review)
                          ▼
                          published   (set by the database when the version publishes)

What a lead holds is only what's needed to go and buy the right pack: product,
brand, variant, size, barcode, where it was seen. The screenshot stays in
research/ as private evidence of why the lead exists; nothing from it is read
into a product version, and the database refuses to publish a version whose
production_source isn't 'physical_label'.
"""

import hashlib
import os
import shutil

import psycopg
from psycopg.rows import dict_row

PLATFORMS = ("Flipkart", "Amazon", "Blinkit", "Zepto", "Swiggy Instamart",
             "BigBasket", "JioMart", "Open Food Facts", "Other")
# Manual steps a person reports. 'published' is only ever set by the database.
_NEXT = {
    "needs_primary_source": {"pack_obtained", "label_captured", "abandoned"},
    "pack_obtained": {"label_captured", "abandoned"},
    "label_captured": {"abandoned"},
}


class LeadError(ValueError):
    pass


def store_screenshot(path, research_dir):
    """Copy a screenshot into research/screenshots/ under its content hash. Returns the hash."""
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    ext = os.path.splitext(path)[1].lower() or ".png"
    dest_dir = os.path.join(research_dir, "screenshots")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, digest + ext)
    if not os.path.exists(dest):
        shutil.copyfile(path, dest)
    return digest


class Leads:
    def __init__(self, conninfo):
        self.conninfo = conninfo

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    def add(self, *, product, noted_by, brand=None, variant=None, net_quantity=None,
            barcode=None, source_type="marketplace_reference", source_platform=None,
            source_url=None, screenshot_sha256=None, notes=None):
        if source_platform and source_platform not in PLATFORMS:
            raise LeadError(f"platform must be one of: {', '.join(PLATFORMS)}")
        if not (product or "").strip():
            raise LeadError("product name is required")
        with self._connect() as c:
            if screenshot_sha256:
                dup = c.execute("SELECT id FROM product_leads WHERE screenshot_sha256 = %s",
                                (screenshot_sha256,)).fetchone()
                if dup:
                    raise LeadError(f"this screenshot is already lead #{dup['id']}")
            if barcode:
                dup = c.execute("""SELECT id FROM product_leads
                                    WHERE barcode = %s AND evidence_status <> 'abandoned'""",
                                (barcode,)).fetchone()
                if dup:
                    raise LeadError(f"barcode {barcode} is already lead #{dup['id']}")
            return c.execute(
                """INSERT INTO product_leads
                     (product, brand, variant, net_quantity, barcode, source_type, source_platform,
                      source_url, screenshot_sha256, noted_by, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (product.strip(), brand, variant, net_quantity, barcode or None, source_type,
                 source_platform, source_url, screenshot_sha256, noted_by, notes)).fetchone()

    def get(self, lead_id):
        with self._connect() as c:
            return c.execute("SELECT * FROM product_leads WHERE id = %s", (lead_id,)).fetchone()

    def list(self, status=None):
        with self._connect() as c:
            if status:
                return c.execute("SELECT * FROM product_leads WHERE evidence_status = %s ORDER BY id",
                                 (status,)).fetchall()
            return c.execute("SELECT * FROM product_leads ORDER BY id").fetchall()

    def counts(self):
        with self._connect() as c:
            rows = c.execute("""SELECT evidence_status, count(*) AS n FROM product_leads
                                 GROUP BY 1""").fetchall()
        return {r["evidence_status"]: r["n"] for r in rows}

    def _move(self, c, lead_id, to, note=None, version_id=None):
        lead = c.execute("SELECT * FROM product_leads WHERE id = %s FOR UPDATE", (lead_id,)).fetchone()
        if lead is None:
            raise LeadError(f"no lead #{lead_id}")
        if to not in _NEXT.get(lead["evidence_status"], set()):
            raise LeadError(f"lead #{lead_id} is {lead['evidence_status']}; it can't move to {to}")
        return c.execute(
            """UPDATE product_leads
                  SET evidence_status = %s, status_note = COALESCE(%s, status_note),
                      product_version_id = COALESCE(%s, product_version_id)
                WHERE id = %s RETURNING *""", (to, note, version_id, lead_id)).fetchone()

    def pack_obtained(self, lead_id, note=None):
        with self._connect() as c:
            return self._move(c, lead_id, "pack_obtained", note)

    def abandon(self, lead_id, reason):
        if not (reason or "").strip():
            raise LeadError("say why the lead is abandoned (e.g. 'not sold offline', 'discontinued')")
        with self._connect() as c:
            return self._move(c, lead_id, "abandoned", reason.strip())

    def link(self, lead_id, *, product_version_id=None, barcode=None):
        """
        Attach the version read from the physical pack. Give the version id, or
        the barcode of the scanned product (its newest version is used).
        If that version is already published, the lead is closed at once.
        """
        with self._connect() as c:
            if product_version_id is None:
                if not barcode:
                    raise LeadError("give a product version id or a barcode")
                row = c.execute(
                    """SELECT v.id FROM product_versions v JOIN products p ON p.id = v.product_id
                        WHERE p.barcode = %s AND v.status <> 'rejected'
                        ORDER BY v.version_no DESC LIMIT 1""", (barcode,)).fetchone()
                if row is None:
                    raise LeadError(f"no scanned product with barcode {barcode}; scan the pack first")
                product_version_id = row["id"]
            v = c.execute("SELECT id, status, production_source FROM product_versions WHERE id = %s",
                          (product_version_id,)).fetchone()
            if v is None:
                raise LeadError(f"no product version #{product_version_id}")
            if v["production_source"] != "physical_label":
                raise LeadError("that version was read from a listing, not a pack; scan the physical label")
            if v["status"] == "rejected":
                raise LeadError(f"version #{v['id']} was rejected in review; scan the pack again")
            lead = self._move(c, lead_id, "label_captured", version_id=v["id"])
            if v["status"] == "published":
                lead = c.execute("""UPDATE product_leads SET evidence_status = 'published'
                                     WHERE id = %s RETURNING *""", (lead_id,)).fetchone()
            return lead

"""
Review queue actions (D-028, D-070, D-076). The only path from a scan to the
public catalogue.

Every action runs in one transaction and only on an item the reviewer has
claimed, so two reviewers can never decide the same item.
"""

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from insidelabel import barcode as barcode_rules
from insidelabel.claims import checker as claim_checker
from insidelabel.core import engine
from insidelabel.db.store import Store, build_findings, claims_hash, ingredients_hash


class ReviewError(Exception):
    """A decision the reviewer can fix (shown on the page, not a crash)."""


def _lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


class ReviewService:
    def __init__(self, conninfo, engine_version):
        self.conninfo = conninfo
        self.engine_version = engine_version

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    # ---------------------------------------------------------------- reads

    def summary(self):
        with self._connect() as c:
            rows = c.execute("""SELECT kind, status, count(*) AS n FROM review_queue
                                 WHERE status IN ('open', 'claimed') GROUP BY kind, status""").fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["kind"], {"open": 0, "claimed": 0})[r["status"]] = r["n"]
        return out

    def list_items(self, status="open", reviewer=None, limit=100):
        with self._connect() as c:
            return c.execute(
                """SELECT q.id, q.kind, q.status, q.created_at, q.claimed_by,
                          p.name AS product_name, p.barcode, b.name AS brand,
                          -- D-106: any photo on this item uploaded rather than taken with the camera
                          EXISTS (SELECT 1 FROM scans s
                                   WHERE (s.id = q.scan_id OR s.id = ANY(q.attempt_scan_ids))
                                     AND s.request->'photo_sources' @? '$.* ? (@ == "upload")') AS uploaded
                     FROM review_queue q
                     LEFT JOIN product_versions v ON v.id = q.product_version_id
                     LEFT JOIN products p ON p.id = v.product_id
                     LEFT JOIN brands b ON b.id = p.brand_id
                    WHERE q.status = %s AND (%s::text IS NULL OR q.claimed_by = %s)
                    ORDER BY q.created_at, q.id LIMIT %s""",
                (status, reviewer, reviewer, limit)).fetchall()

    def get(self, item_id):
        """Everything the reviewer needs on one page, or None."""
        with self._connect() as c:
            q = c.execute("SELECT * FROM review_queue WHERE id = %s", (item_id,)).fetchone()
            if q is None:
                return None
            v = p = current = scan = corr = None
            if q["product_version_id"]:
                v = c.execute("SELECT * FROM product_versions WHERE id = %s",
                              (q["product_version_id"],)).fetchone()
                p = c.execute("""SELECT p.*, b.name AS brand, k.code AS category_code FROM products p
                                   LEFT JOIN brands b ON b.id = p.brand_id
                                   LEFT JOIN categories k ON k.id = p.category_id WHERE p.id = %s""",
                              (v["product_id"],)).fetchone()
                current = c.execute("""SELECT * FROM product_versions
                                        WHERE product_id = %s AND is_current AND id <> %s""",
                                    (v["product_id"], v["id"])).fetchone()
            if q["scan_id"]:
                scan = c.execute("SELECT * FROM scans WHERE id = %s", (q["scan_id"],)).fetchone()
            # D-070: the earlier refused attempts of a pack sent to us, oldest first.
            attempts = c.execute(
                """SELECT id, back_image_key, front_image_key, created_at, error_code, request FROM scans
                    WHERE id = ANY(%s) ORDER BY created_at""",
                (q.get("attempt_scan_ids") or [],)).fetchall()
            if q["correction_id"]:
                corr = c.execute("SELECT * FROM corrections WHERE id = %s", (q["correction_id"],)).fetchone()
            leads = []
            if v:
                # D-089: the marketplace leads this pack was bought to answer.
                leads = c.execute(
                    """SELECT l.id, l.source_platform, l.source_type, l.source_url, l.captured_on,
                              l.evidence_status
                         FROM product_leads l JOIN product_versions lv ON lv.id = l.product_version_id
                        WHERE lv.product_id = %s ORDER BY l.id""", (v["product_id"],)).fetchall()
            findings = []
            if v:
                findings = c.execute(
                    """SELECT f.tier, f.kind, f.severity, f.rendered_text,
                              array_agg(e.quoted_text ORDER BY e.id) AS quotes
                         FROM findings f
                         JOIN finding_evidence fe ON fe.finding_id = f.id
                         JOIN evidence e ON e.id = fe.evidence_id
                        WHERE f.product_version_id = %s
                        GROUP BY f.id ORDER BY f.id""", (v["id"],)).fetchall()
        images = {
            "back": (v and v["back_image_key"]) or (scan and scan["back_image_key"]),
            "front": (v and v["front_image_key"]) or (scan and scan["front_image_key"]),
        }
        return {"item": q, "version": v, "product": p, "current": current, "scan": scan,
                "correction": corr, "findings": findings, "images": images, "leads": leads,
                "attempts": attempts}

    # ---------------------------------------------------------------- claiming

    def claim_next(self, reviewer):
        with self._connect() as c:
            r = c.execute("SELECT id FROM claim_next_review(%s)", (reviewer,)).fetchone()
            return r["id"] if r else None

    def claim(self, item_id, reviewer):
        with self._connect() as c:
            r = c.execute("""UPDATE review_queue SET status = 'claimed', claimed_by = %s, claimed_at = now()
                              WHERE id = %s AND status = 'open' RETURNING id""",
                          (reviewer, item_id)).fetchone()
            return r is not None

    def release(self, item_id, reviewer):
        with self._connect() as c:
            self._mine(c, item_id, reviewer)
            c.execute("""UPDATE review_queue SET status = 'open', claimed_by = NULL, claimed_at = NULL
                          WHERE id = %s""", (item_id,))

    @staticmethod
    def _mine(c, item_id, reviewer):
        q = c.execute("SELECT * FROM review_queue WHERE id = %s FOR UPDATE", (item_id,)).fetchone()
        if q is None:
            raise ReviewError("No such item.")
        if q["status"] != "claimed" or q["claimed_by"] != reviewer:
            raise ReviewError("Claim this item before deciding it.")
        return q

    # ---------------------------------------------------------------- decisions

    def reject(self, item_id, reviewer, reason):
        if not (reason or "").strip():
            raise ReviewError("Say why it is rejected; the note is kept with the decision.")
        with self._connect() as c:
            q = self._mine(c, item_id, reviewer)
            if q["product_version_id"]:
                c.execute("""UPDATE product_versions SET status = 'rejected'
                              WHERE id = %s AND status = 'pending_review'""", (q["product_version_id"],))
            if q["correction_id"]:
                c.execute("""UPDATE corrections SET status = 'rejected', reviewed_by = %s, reviewed_at = now()
                              WHERE id = %s""", (reviewer, q["correction_id"]))
            self._close(c, item_id, "rejected", "rejected", reason.strip(), None)

    def approve(self, item_id, reviewer, form):
        """
        form: name, brand, variant, barcode, ingredients (one per line),
              allergen_statement, front_claims (one per line), category (FSSAI code), note
        """
        ingredients = _lines(form.get("ingredients"))
        if not ingredients:
            raise ReviewError("The ingredient list is empty. Transcribe it from the photo.")
        raw = ", ".join(ingredients)
        if not engine.tokenize(raw):
            raise ReviewError("No ingredients could be parsed from that list.")
        claims = _lines(form.get("front_claims"))
        statement = (form.get("allergen_statement") or "").strip() or None
        barcode = (form.get("barcode") or "").strip() or None
        if barcode:
            # D-103: a reviewer's typo would file the pack under someone else's product.
            barcode, reason = barcode_rules.check(barcode)
            if reason:
                raise ReviewError(f"Barcode: {barcode_rules.MESSAGES[reason]}")

        with self._connect() as c:
            q = self._mine(c, item_id, reviewer)
            v = (c.execute("SELECT * FROM product_versions WHERE id = %s FOR UPDATE",
                           (q["product_version_id"],)).fetchone() if q["product_version_id"] else None)
            if v and v["status"] == "rejected":
                raise ReviewError("This version was rejected earlier; it can't be published.")
            if v and v.get("production_source", "physical_label") != "physical_label":
                # D-089: a listing is a lead, not a source. Photograph the pack.
                raise ReviewError("This was read from an online listing, not the pack. "
                                  "Reject it and scan the physical label instead.")

            pid = v["product_id"] if v else None
            if pid is None and not barcode:
                # D-107: the catalogue is filed by barcode. A new product without
                # one could never be found again by a scan.
                raise ReviewError("A new product needs its barcode. Read it from the photos; "
                                  "if no photo shows one, reject the item.")
            pid = self._save_product(c, pid, form, barcode)
            content = (ingredients_hash(ingredients), statement, claims_hash(claims))

            if v and v["status"] == "pending_review":
                # Correct the waiting version in place, then publish it.
                self._write_version(c, v["id"], ingredients, statement, claims)
                c.execute("SELECT publish_version(%s, %s)", (v["id"], reviewer))
                vid, resolution = v["id"], "published"
            elif (v and (v["ingredients_hash"], v["allergen_statement"], v["claims_hash"]) == content
                  # D-100: a front with no claims is still news: the new version
                  # records the photo, so the app stops asking for it.
                  and not (q["kind"] == "front_photo" and not v["front_image_key"])):
                vid, resolution = v["id"], "no_change"        # a correction that changed nothing
            else:
                # Published (or no) version: history is kept, so a change is a new version.
                src = v or {}
                scan = (c.execute("SELECT * FROM scans WHERE id = %s", (q["scan_id"],)).fetchone()
                        if q["scan_id"] else None) or {}
                n = c.execute("SELECT COALESCE(max(version_no), 0) + 1 AS n FROM product_versions "
                              "WHERE product_id = %s", (pid,)).fetchone()["n"]
                vid = c.execute(
                    """INSERT INTO product_versions
                         (product_id, version_no, ingredient_lines, ingredients, ingredients_hash,
                          engine_version, source, status, front_image_key, back_image_key, raw_extraction)
                       VALUES (%s, %s, %s, %s, %s, %s, 'reviewer', 'pending_review', %s, %s, %s)
                       RETURNING id""",
                    (pid, n, Jsonb(ingredients), Jsonb(ingredients), content[0], self.engine_version,
                     src.get("front_image_key") or scan.get("front_image_key"),
                     src.get("back_image_key") or scan.get("back_image_key"),
                     Jsonb({"derived_from_version": src.get("id"), "review_item": item_id}))).fetchone()["id"]
                self._write_version(c, vid, ingredients, statement, claims)
                c.execute("SELECT publish_version(%s, %s)", (vid, reviewer))
                resolution = "published_new_version"

            if q["correction_id"]:
                c.execute("""UPDATE corrections SET status = %s, reviewed_by = %s, reviewed_at = now()
                              WHERE id = %s""",
                          ("rejected" if resolution == "no_change" else "accepted", reviewer, q["correction_id"]))
            self._close(c, item_id, "done", resolution, (form.get("note") or "").strip() or None, vid)
            return {"product_version_id": vid, "resolution": resolution}

    # ---------------------------------------------------------------- helpers

    def categories(self):
        """Every FSSAI food category as (code, name, depth), in the regulation's order."""
        with self._connect() as c:
            rows = c.execute("SELECT code, name FROM categories").fetchall()
        key = lambda r: [int(x) for x in r["code"].split(".")]      # noqa: E731 - 7.2.10 after 7.2.9
        return [(r["code"], r["name"], r["code"].count(".")) for r in sorted(rows, key=key)]

    def _save_product(self, c, pid, form, barcode):
        name = (form.get("name") or "").strip()
        if not name:
            raise ReviewError("Product name is required.")
        # D-058 / release gate: every published product has an FSSAI food category.
        code = (form.get("category") or "").strip()
        if not code:
            raise ReviewError("Pick the product's FSSAI food category.")
        cat = c.execute("SELECT id FROM categories WHERE code = %s", (code,)).fetchone()
        if cat is None:
            raise ReviewError(f"Unknown food category {code!r}.")
        if barcode:
            other = c.execute("SELECT id, name FROM products WHERE barcode = %s AND id IS DISTINCT FROM %s",
                              (barcode, pid)).fetchone()
            if other:
                raise ReviewError(f"Barcode {barcode} already belongs to product #{other['id']} "
                                  f"({other['name']}).")
        brand_id = None
        if (form.get("brand") or "").strip():
            brand_id = c.execute(
                """INSERT INTO brands (name) VALUES (%s)
                   ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                (form["brand"].strip(),)).fetchone()["id"]
        variant = (form.get("variant") or "").strip() or None
        if pid is None:
            return c.execute("""INSERT INTO products (barcode, brand_id, name, variant, category_id)
                                VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                             (barcode, brand_id, name, variant, cat["id"])).fetchone()["id"]
        c.execute("""UPDATE products SET name = %s, brand_id = %s, variant = %s,
                            barcode = COALESCE(%s, barcode), category_id = %s WHERE id = %s""",
                  (name, brand_id, variant, barcode, cat["id"], pid))
        return pid

    def _write_version(self, c, vid, ingredients, statement, claims):
        """Set a waiting version's content and rebuild its findings from it."""
        raw = ", ".join(ingredients)
        verdict = engine.analyze(raw)
        cc = claim_checker.check_claims(claims, raw, verdict, "read" if claims else "not_provided")
        c.execute("""UPDATE product_versions
                        SET ingredients = %s, ingredient_lines = %s, ingredients_hash = %s,
                            allergen_statement = %s, front_claims = %s, claims_hash = %s,
                            engine_version = %s
                      WHERE id = %s AND status = 'pending_review'""",
                  (Jsonb(ingredients), Jsonb(ingredients), ingredients_hash(ingredients), statement,
                   Jsonb(claims), claims_hash(claims), self.engine_version, vid))
        c.execute("DELETE FROM findings WHERE product_version_id = %s", (vid,))
        c.execute("DELETE FROM evidence WHERE product_version_id = %s", (vid,))
        Store._insert_findings(c, vid, self.engine_version,
                               build_findings(ingredients, verdict, cc, self.engine_version))

    @staticmethod
    def _close(c, item_id, status, resolution, note, vid):
        c.execute("""UPDATE review_queue
                        SET status = %s, resolution = %s, resolution_note = %s,
                            resolved_product_version_id = %s, resolved_at = now()
                      WHERE id = %s""", (status, resolution, note, vid, item_id))

    # ---------------------------------------------------------------- D-070

    def updates_for(self, device_id, limit=20):
        """Finished items this install asked about, newest first."""
        with self._connect() as c:
            return c.execute(
                """SELECT q.id AS review_id, q.kind, q.resolution, q.resolved_at,
                          q.resolved_product_version_id AS product_version_id,
                          p.name AS product_name, p.barcode
                     FROM review_queue q
                     LEFT JOIN product_versions v ON v.id = q.resolved_product_version_id
                     LEFT JOIN products p ON p.id = v.product_id
                    WHERE q.notify_user_id = %s AND q.status IN ('done', 'rejected')
                    ORDER BY q.resolved_at DESC LIMIT %s""", (device_id, limit)).fetchall()

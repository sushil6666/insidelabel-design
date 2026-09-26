"""
Persistence for the scan path (D-020, D-024, D-026, D-028, D-043, D-076).

The API calls this only when INSIDELABEL_DB is set; without it the API works
exactly as before and nothing is stored.

Rules this module follows (the database enforces the hard ones too):
  * A scan result becomes a product version waiting for review, never a public
    catalogue entry by itself (D-028). An identical version already waiting is
    reused, so one pack scanned by many people is reviewed once.
  * A new ingredient list on a product that already has a published version is
    a reformulation (D-026) and is queued as such.
  * Every finding is stored with at least one evidence row pointing at the
    label's own words (D-043).
  * Front-of-pack claims are stored only when the claim check actually ran on a
    confirmed pairing (D-035); otherwise they may belong to a different pack.
  * Every scan row carries its own trace (D-092): request id, build, data
    version, the model's raw answer, the independent reader's text (007) and
    the request options, so any scan can be replayed later (tools/repro.py).
  * A front photo for a published version that has none is queued for a
    reviewer as 'front_photo' (D-100), once per version: the claims database is
    built from real packs, one front per version, never one per scan.
"""

import hashlib
import re
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from insidelabel.core import engine
from insidelabel.core.tokenize import extract_ins

# ---------------------------------------------------------------- fingerprints


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def ingredients_hash(ingredients):
    """Stable fingerprint of an ingredient list: order matters, case and spacing don't."""
    return hashlib.sha256("|".join(_norm(i) for i in ingredients).encode()).hexdigest()


def claims_hash(claims):
    if not claims:
        return None
    return hashlib.sha256("|".join(sorted(_norm(c) for c in claims)).encode()).hexdigest()


# ---------------------------------------------------------------- findings

_CLAIM_TIER = {"made_with_real": "R4"}      # unregulated marketing; the rest are non-addition (R2)
_INS_IN_TEXT = re.compile(r"\bINS (\w+)")


def _ins_of_entry(entry):
    return {extract_ins(t) for t in engine.tokenize(entry)} - {None}


def _position(ingredients, ins=None, text=None):
    """1-based position of the ingredient entry holding an INS number or text."""
    for i, entry in enumerate(ingredients, start=1):
        if ins and ins in _ins_of_entry(entry):
            return i
    if text:
        t = _norm(re.sub(r"[()\[\]{}]", " ", text))
        for i, entry in enumerate(ingredients, start=1):
            if t and t in _norm(entry):
                return i
    return None


def _ingredient_evidence(ingredients, ins=None, text=None):
    pos = _position(ingredients, ins=ins, text=text)
    if pos:
        return {"kind": "ingredient", "pointer": {"ingredient_position": pos},
                "quoted_text": ingredients[pos - 1]}
    return {"kind": "ingredient", "pointer": {"token": text or ins}, "quoted_text": text or ins}


def build_findings(ingredients, verdict, claim_check, engine_version):
    """
    Turn one analysed label into finding rows, each with its evidence.
    Pure: no database. Every row returned has at least one evidence item.
    """
    rule_version = f"engine {engine_version} / additives.json {engine.ADDITIVES['_meta']['version']}"
    out = []

    for f in verdict.get("flags", []):
        m = _INS_IN_TEXT.search(f.get("matched_as", ""))
        if f["type"] == "nova_marker":
            tier, kind, code = "R3", "fact", "NOVA:" + f["matched_as"].split(": ", 1)[-1]
        else:
            tier = "ING"
            kind = "potential_concern" if f["concern"] in ("moderate", "high") else "fact"
            code = f"ADDITIVE:INS {m.group(1)}" if m else "ADDITIVE:" + f["matched_as"]
        out.append({
            "rule_code": code, "rule_version": rule_version, "tier": tier, "kind": kind,
            "severity": f["concern"],
            "rendered_text": f"{f['matched_as']}. {f['why']}",
            "evidence": [_ingredient_evidence(ingredients, ins=m.group(1) if m else None,
                                              text=f.get("ingredient"))],
        })

    if (claim_check or {}).get("status") == "checked":
        for idx, ch in enumerate(claim_check["checked"]):
            if not ch["contradicted"]:
                continue
            ev = [{"kind": "claim", "pointer": {"claim_index": idx}, "quoted_text": ch["claim"]}]
            facts = []
            for c in ch["contradicted_by"]:
                facts.append(c["fact"])
                src = c.get("evidence")
                if src:
                    m = _INS_IN_TEXT.search(src)
                    ev.append(_ingredient_evidence(ingredients, ins=m.group(1) if m else None, text=src))
            out.append({
                "rule_code": "CLAIM:" + ch["rule_id"], "rule_version": rule_version,
                "tier": _CLAIM_TIER.get(ch["rule_id"], "R2"), "kind": "fact",
                "severity": "contradiction",
                # D-042 template: "The label claims X. The declaration says Y."
                "rendered_text": f"The label claims \"{ch['claim']}\". " + " ".join(facts),
                "evidence": ev,
            })
    return out


# ---------------------------------------------------------------- store


class Store:
    def __init__(self, conninfo):
        self.conninfo = conninfo

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    # -- users ---------------------------------------------------------

    @staticmethod
    def _user(conn, device_id):
        """The anonymous install id, created on first sight. Invalid ids are ignored."""
        if not device_id:
            return None
        try:
            uid = str(uuid.UUID(str(device_id)))
        except ValueError:
            return None
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (uid,))
        return uid

    # -- reads ---------------------------------------------------------

    # D-100: the app asks for the front only when this version has none and no
    # front photo is already waiting for a reviewer.
    _FRONT_WANTED = """v.front_image_key IS NULL AND NOT EXISTS (
                          SELECT 1 FROM review_queue fq
                           WHERE fq.kind = 'front_photo' AND fq.product_version_id = v.id
                             AND fq.status IN ('open', 'claimed')) AS front_wanted"""

    def find_current(self, barcode):
        """The published, current version for a barcode, or None (D-024)."""
        with self._connect() as conn:
            return conn.execute(
                """SELECT p.id AS product_id, p.barcode, p.name, p.variant, b.name AS brand,
                          p.net_qty_value, p.net_qty_unit,
                          v.id AS product_version_id, v.version_no, v.ingredients,
                          v.allergen_statement, v.front_claims, v.verified_at, """ + self._FRONT_WANTED + """
                     FROM products p
                     JOIN product_versions v ON v.product_id = p.id AND v.is_current
                     LEFT JOIN brands b ON b.id = p.brand_id
                    WHERE p.barcode = %s""", (barcode,)).fetchone()

    def version_hit(self, product_version_id):
        """A specific version in find_current()'s shape: what a cached scan was served (D-092)."""
        with self._connect() as conn:
            return conn.execute(
                """SELECT p.id AS product_id, p.barcode, p.name, p.variant, b.name AS brand,
                          p.net_qty_value, p.net_qty_unit,
                          v.id AS product_version_id, v.version_no, v.ingredients,
                          v.allergen_statement, v.front_claims, v.verified_at, """ + self._FRONT_WANTED + """
                     FROM product_versions v
                     JOIN products p ON p.id = v.product_id
                     LEFT JOIN brands b ON b.id = p.brand_id
                    WHERE v.id = %s""", (product_version_id,)).fetchone()

    # -- writes --------------------------------------------------------

    def record_cache_hit(self, hit, device_id=None, latency_ms=None, trace=None):
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            conn.execute("UPDATE products SET scan_count = scan_count + 1 WHERE id = %s",
                         (hit["product_id"],))
            sid = conn.execute(
                """INSERT INTO scans (user_id, product_version_id, resolved_via, cache_hit, outcome,
                                      latency_ms, ai_cost_paise)
                   VALUES (%s, %s, 'barcode', true, 'verdict', %s, 0) RETURNING id""",
                (uid, hit["product_version_id"], latency_ms)).fetchone()["id"]
            self._set_trace(conn, sid, trace)
            return sid

    def add_front(self, hit, *, front_key, device_id=None, latency_ms=None, trace=None):
        """
        D-100: a front photo for a catalogue product, sent with its barcode and
        nothing else. No model call: a reviewer reads the claims off the photo,
        against the back photo already on file. Queued once per version.
        Returns {"scan_id", "queued"}: queued is None when one is already waiting.
        """
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            conn.execute("UPDATE products SET scan_count = scan_count + 1 WHERE id = %s",
                         (hit["product_id"],))
            sid = conn.execute(
                """INSERT INTO scans (user_id, product_version_id, resolved_via, cache_hit, outcome,
                                      latency_ms, ai_cost_paise, front_image_key)
                   VALUES (%s, %s, 'barcode', true, 'verdict', %s, 0, %s) RETURNING id""",
                (uid, hit["product_version_id"], latency_ms, front_key)).fetchone()["id"]
            self._set_trace(conn, sid, trace)
            queued = self._queue_front(conn, hit["product_version_id"], sid, uid)
            return {"scan_id": str(sid), "queued": queued}

    @staticmethod
    def _queue_front(conn, vid, sid, uid):
        """'front_photo' for a version without a front, unless one is waiting. Locks the version row."""
        v = conn.execute("SELECT front_image_key FROM product_versions WHERE id = %s FOR UPDATE",
                         (vid,)).fetchone()
        if v is None or v["front_image_key"]:
            return None
        waiting = conn.execute(
            """SELECT 1 FROM review_queue WHERE kind = 'front_photo' AND product_version_id = %s
                  AND status IN ('open', 'claimed')""", (vid,)).fetchone()
        if waiting:
            return None
        conn.execute("""INSERT INTO review_queue (kind, scan_id, product_version_id, notify_user_id)
                        VALUES ('front_photo', %s, %s, %s)""", (sid, vid, uid))
        return "front_photo"

    def record_failed_scan(self, outcome, error_code=None, device_id=None, latency_ms=None,
                           front_key=None, back_key=None, trace=None):
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            sid = conn.execute(
                """INSERT INTO scans (user_id, resolved_via, cache_hit, outcome, error_code, latency_ms,
                                      front_image_key, back_image_key)
                   VALUES (%s, 'failed', false, %s, %s, %s, %s, %s) RETURNING id""",
                (uid, outcome, error_code, latency_ms, front_key, back_key)).fetchone()["id"]
            self._set_trace(conn, sid, trace)
            return sid

    def save_scan(self, *, vision, verdict, claim_check, claims_trusted, reliability,
                  barcode=None, device_id=None, latency_ms=None,
                  model_name=None, prompt_version=None, engine_version=None,
                  front_key=None, back_key=None, trace=None):
        """
        Store a vision-path scan: product (found or created), a version waiting
        for review (new, or an identical one already waiting), its findings and
        evidence, a review-queue item, and the scan row. One transaction.
        """
        ingredients = vision["ingredients"]
        ihash = ingredients_hash(ingredients)
        product_meta = vision.get("product") or {}
        front_claims = vision.get("front_claims", []) if claims_trusted else []

        with self._connect() as conn:
            uid = self._user(conn, device_id)
            product = None
            if barcode:
                product = conn.execute("SELECT id FROM products WHERE barcode = %s FOR UPDATE",
                                       (barcode,)).fetchone()
            if product is None:
                brand_id = None
                if product_meta.get("brand"):
                    brand_id = conn.execute(
                        """INSERT INTO brands (name) VALUES (%s)
                           ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                        (product_meta["brand"].strip(),)).fetchone()["id"]
                product = conn.execute(
                    """INSERT INTO products (barcode, brand_id, name, variant)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (barcode or None, brand_id,
                     (product_meta.get("name") or "Unknown product").strip(),
                     product_meta.get("variant"))).fetchone()
            pid = product["id"]
            conn.execute("UPDATE products SET scan_count = scan_count + 1 WHERE id = %s", (pid,))

            current = conn.execute(
                "SELECT id, ingredients_hash FROM product_versions WHERE product_id = %s AND is_current",
                (pid,)).fetchone()
            pending = conn.execute(
                """SELECT id FROM product_versions
                    WHERE product_id = %s AND status = 'pending_review' AND ingredients_hash = %s""",
                (pid, ihash)).fetchone()

            queued = None
            front_for_review = False
            if current and current["ingredients_hash"] == ihash:
                # A re-read of a published pack (e.g. the D-073 allergy
                # re-check) found the same label. Nothing new to review,
                # unless it brought the front this version lacks (D-100).
                vid, vstatus = current["id"], "published"
                front_for_review = bool(front_key and claims_trusted)
            elif pending:
                vid, vstatus = pending["id"], "pending_review"
                if front_key and claims_trusted:
                    # The reviewer of the waiting version gets the front too (D-100).
                    conn.execute("""UPDATE product_versions SET front_image_key = %s
                                     WHERE id = %s AND front_image_key IS NULL""", (front_key, vid))
            else:
                n = conn.execute("SELECT COALESCE(max(version_no), 0) + 1 AS n FROM product_versions "
                                 "WHERE product_id = %s", (pid,)).fetchone()["n"]
                raw = {k: v for k, v in vision.items() if k != "_ocr_cross_check"}
                raw["_reliability"] = reliability
                vid = conn.execute(
                    """INSERT INTO product_versions
                         (product_id, version_no, ingredient_lines, ingredients, allergen_statement,
                          front_claims, raw_extraction, ingredients_hash, claims_hash,
                          model_name, prompt_version, engine_version, source, status,
                          front_image_key, back_image_key)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'scan', 'pending_review', %s, %s)
                       RETURNING id""",
                    (pid, n, Jsonb(vision.get("ingredient_lines") or ingredients), Jsonb(ingredients),
                     vision.get("allergen_statement"), Jsonb(front_claims), Jsonb(raw), ihash,
                     claims_hash(front_claims), model_name, prompt_version, engine_version,
                     front_key if claims_trusted else None, back_key)).fetchone()["id"]
                vstatus = "pending_review"
                self._insert_findings(conn, vid, engine_version, build_findings(
                    ingredients, verdict, claim_check if claims_trusted else None, engine_version))
                queued = "reformulation" if current else "new_product"

            sid = conn.execute(
                """INSERT INTO scans (user_id, product_version_id, resolved_via, cache_hit, outcome,
                                      latency_ms, front_image_key, back_image_key)
                   VALUES (%s, %s, %s, false, 'verdict', %s, %s, %s) RETURNING id""",
                (uid, vid, "new_product" if vstatus == "pending_review" else "barcode",
                 latency_ms, front_key, back_key)).fetchone()["id"]
            self._set_trace(conn, sid, trace)
            if front_for_review:
                queued = self._queue_front(conn, vid, sid, uid)
            if queued and queued != "front_photo":
                conn.execute(
                    """INSERT INTO review_queue (kind, scan_id, product_version_id, notify_user_id)
                       VALUES (%s, %s, %s, %s)""", (queued, sid, vid, uid))
            return {"scan_id": str(sid), "product_id": pid, "product_version_id": vid,
                    "version_status": vstatus, "queued": queued}

    _TRACE_COLS = ("request_id", "build", "data_version", "engine_version", "prompt_version",
                   "model_raw", "request", "timings", "ocr")

    @classmethod
    def _set_trace(cls, conn, sid, trace):
        """D-092: what it takes to replay this scan. Unknown keys are ignored."""
        if not trace:
            return
        cols = [c for c in cls._TRACE_COLS if trace.get(c) is not None]
        if not cols:
            return
        vals = [Jsonb(trace[c]) if c in ("request", "timings", "ocr") else trace[c] for c in cols]
        conn.execute(f"UPDATE scans SET {', '.join(c + ' = %s' for c in cols)} WHERE id = %s",
                     (*vals, sid))

    @staticmethod
    def _insert_findings(conn, vid, engine_version, findings):
        for f in findings:
            fid = conn.execute(
                """INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                         severity, rendered_text, engine_version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (vid, f["rule_code"], f["rule_version"], f["tier"], f["kind"], f["severity"],
                 f["rendered_text"], engine_version)).fetchone()["id"]
            for e in f["evidence"]:
                eid = conn.execute(
                    """INSERT INTO evidence (product_version_id, kind, pointer, quoted_text)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (vid, e["kind"], Jsonb(e["pointer"]), e.get("quoted_text"))).fetchone()["id"]
                conn.execute("INSERT INTO finding_evidence VALUES (%s, %s) ON CONFLICT DO NOTHING",
                             (fid, eid))

    def report(self, *, scan_id=None, product_version_id=None, device_id=None,
               field, proposed_value=None, note=None):
        """D-076 'Report a mistake': a correction plus a review-queue item. None if unknown scan."""
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            if scan_id:
                row = conn.execute("SELECT product_version_id FROM scans WHERE id = %s",
                                   (scan_id,)).fetchone()
                if row is None:
                    return None
                product_version_id = product_version_id or row["product_version_id"]
            elif product_version_id:
                if conn.execute("SELECT 1 FROM product_versions WHERE id = %s",
                                (product_version_id,)).fetchone() is None:
                    return None
            cid = conn.execute(
                """INSERT INTO corrections (scan_id, product_version_id, user_id, field, proposed_value, note)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (scan_id, product_version_id, uid, field, proposed_value, note)).fetchone()["id"]
            rid = conn.execute(
                """INSERT INTO review_queue (kind, scan_id, product_version_id, correction_id, notify_user_id)
                   VALUES ('correction', %s, %s, %s, %s) RETURNING id""",
                (scan_id, product_version_id, cid, uid)).fetchone()["id"]
            return {"correction_id": cid, "review_id": rid}

    # -- invite-only beta (D-102) -------------------------------------------

    CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"     # no 0/O, 1/I/L: read aloud, typed from a message

    @staticmethod
    def clean_code(code):
        return re.sub(r"[^A-Z0-9]", "", (code or "").upper())

    def create_invites(self, n, label=None, max_devices=3):
        import secrets
        codes = []
        with self._connect() as conn:
            while len(codes) < n:
                code = "".join(secrets.choice(self.CODE_ALPHABET) for _ in range(8))
                if conn.execute("""INSERT INTO invites (code, label, max_devices) VALUES (%s, %s, %s)
                                   ON CONFLICT DO NOTHING RETURNING code""",
                                (code, label, max_devices)).fetchone():
                    codes.append(code)
        return codes

    def join_invite(self, code, device_id):
        """{"joined": True} or {"error": "bad_code" | "revoked" | "code_full"}."""
        code = self.clean_code(code)
        with self._connect() as conn:
            inv = conn.execute("SELECT * FROM invites WHERE code = %s FOR UPDATE", (code,)).fetchone()
            if inv is None:
                return {"error": "bad_code"}
            if inv["revoked_at"]:
                return {"error": "revoked"}
            uid = self._user(conn, device_id)
            mine = conn.execute("SELECT code FROM invite_devices WHERE user_id = %s", (uid,)).fetchone()
            if mine and mine["code"] == code:
                return {"joined": True}
            n = conn.execute("SELECT count(*) AS n FROM invite_devices WHERE code = %s", (code,)).fetchone()["n"]
            if n >= inv["max_devices"]:
                return {"error": "code_full"}
            conn.execute("""INSERT INTO invite_devices (user_id, code) VALUES (%s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET code = EXCLUDED.code, joined_at = now()""",
                         (uid, code))
            return {"joined": True}

    def invite_of(self, device_id):
        """The active code this install joined with, or None."""
        try:
            uid = str(uuid.UUID(str(device_id)))
        except (ValueError, TypeError):
            return None
        with self._connect() as conn:
            r = conn.execute("""SELECT d.code FROM invite_devices d JOIN invites i ON i.code = d.code
                                 WHERE d.user_id = %s AND i.revoked_at IS NULL""", (uid,)).fetchone()
        return r["code"] if r else None

    def revoke_invite(self, code):
        with self._connect() as conn:
            return conn.execute("UPDATE invites SET revoked_at = now() WHERE code = %s RETURNING code",
                                (self.clean_code(code),)).fetchone() is not None

    def reset_invite(self, code):
        """Forget the installs on a code (a tester's new phone, a cleared browser)."""
        with self._connect() as conn:
            return conn.execute("DELETE FROM invite_devices WHERE code = %s",
                                (self.clean_code(code),)).rowcount

    def save_feedback(self, *, device_id, comment, rating=None, screen=None, app_version=None):
        code = self.invite_of(device_id)
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            return conn.execute(
                """INSERT INTO feedback (user_id, invite_code, rating, comment, screen, app_version)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (uid, code, rating, comment, screen, app_version)).fetchone()["id"]

    def beta_testers(self):
        """One row per code: installs, scans, days active, last scan, feedback — the W4 view (D-055)."""
        with self._connect() as conn:
            return conn.execute(
                """SELECT i.code, i.label, i.revoked_at, i.created_at,
                          count(DISTINCT d.user_id) AS devices,
                          count(DISTINCT s.id) AS scans,
                          count(DISTINCT s.created_at::date) AS days_active,
                          min(s.created_at) AS first_scan, max(s.created_at) AS last_scan,
                          (SELECT count(*) FROM feedback f WHERE f.invite_code = i.code) AS feedback
                     FROM invites i
                     LEFT JOIN invite_devices d ON d.code = i.code
                     LEFT JOIN scans s ON s.user_id = d.user_id
                    GROUP BY i.code ORDER BY i.created_at, i.code""").fetchall()

    def feedback_list(self, limit=100):
        with self._connect() as conn:
            return conn.execute(
                """SELECT f.id, f.created_at, f.rating, f.comment, f.screen, f.invite_code, i.label
                     FROM feedback f LEFT JOIN invites i ON i.code = f.invite_code
                    ORDER BY f.created_at DESC LIMIT %s""", (limit,)).fetchall()

    # -- send it to us (D-070) ----------------------------------------------

    SEND_OUTCOMES = ("refused", "vision_failed")      # the read failed; a person can still read the photo

    def send_to_us(self, *, device_id, scan_ids):
        """
        Queue a pack the app couldn't read. Checks what the app claims: the
        scans are this install's own, every one was refused, at least two, and
        the photos exist. Returns {"review_id", "duplicate"?} or {"error": code}.
        """
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            rows = conn.execute(
                """SELECT id, user_id, outcome, back_image_key, created_at FROM scans
                    WHERE id = ANY(%s::uuid[]) ORDER BY created_at, id""", (scan_ids,)).fetchall()
            # Someone else's scan looks exactly like one that doesn't exist.
            if len(rows) != len(scan_ids) or any(str(r["user_id"]) != uid for r in rows):
                return {"error": "not_found"}
            if any(r["outcome"] not in self.SEND_OUTCOMES for r in rows):
                return {"error": "not_refused"}
            if len(rows) < 2:
                return {"error": "need_two_attempts"}
            if not rows[-1]["back_image_key"]:
                return {"error": "no_photo"}
            ids = [r["id"] for r in rows]
            dup = conn.execute(
                """SELECT id FROM review_queue
                    WHERE kind = 'send_to_us' AND (scan_id = ANY(%s) OR attempt_scan_ids && %s)
                    LIMIT 1""", (ids, ids)).fetchone()
            if dup:
                return {"review_id": dup["id"], "duplicate": True}
            rid = conn.execute(
                """INSERT INTO review_queue (kind, scan_id, attempt_scan_ids, notify_user_id)
                   VALUES ('send_to_us', %s, %s, %s) RETURNING id""",
                (ids[-1], ids[:-1], uid)).fetchone()["id"]
            # D-080: the user sent these photos to be read by a person; they are
            # the only copy of the label we have, so they outlive the 30-day rule.
            conn.execute("UPDATE scans SET evidence_hold = true WHERE id = ANY(%s)", (ids,))
            return {"review_id": rid}

    # -- problem reports (D-092) --------------------------------------------

    def save_problem(self, *, kind, device_id=None, scan_id=None, request_id=None, comment=None,
                     app_version=None, build=None, data_version=None, client=None, events=None,
                     server_error=None, signature=None):
        """Store a problem report. A user report holds the scan's photos past retention (D-080)."""
        with self._connect() as conn:
            uid = self._user(conn, device_id)
            # One crash can fire on every screen; an automatic report of the same
            # error from the same phone within an hour is counted once.
            # A setup alarm ('server') fires on every scan until fixed: once an hour is enough.
            if kind in ("auto", "server") and signature:
                dup = conn.execute(
                    """SELECT id FROM problem_reports WHERE kind = %s AND signature = %s
                          AND user_id IS NOT DISTINCT FROM %s AND created_at > now() - interval '1 hour'
                        LIMIT 1""", (kind, signature, uid)).fetchone()
                if dup:
                    return {"problem_id": dup["id"], "scan_id": None, "duplicate": True}
            if scan_id is None and request_id:
                row = conn.execute("SELECT id FROM scans WHERE request_id = %s ORDER BY created_at DESC LIMIT 1",
                                   (request_id,)).fetchone()
                scan_id = row["id"] if row else None
            elif scan_id is not None and conn.execute(
                    "SELECT 1 FROM scans WHERE id = %s", (scan_id,)).fetchone() is None:
                scan_id = None                   # a scan we never stored; keep the report anyway
            pid = conn.execute(
                """INSERT INTO problem_reports (kind, user_id, scan_id, request_id, comment, app_version,
                                                build, data_version, client, events, server_error, signature)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (kind, uid, scan_id, request_id, comment, app_version, build, data_version,
                 Jsonb(client or {}), Jsonb(events or []), server_error, signature)).fetchone()["id"]
            if kind == "user":
                # Every scan in the trail, not just the last: the earlier one may be the cause.
                rids = [e.get("request_id") for e in (events or []) if isinstance(e, dict) and e.get("request_id")]
                conn.execute("""UPDATE scans SET evidence_hold = true
                                 WHERE id = %s OR request_id = ANY(%s)""", (scan_id, rids))
            return {"problem_id": pid, "scan_id": str(scan_id) if scan_id else None}

    def problem(self, problem_id):
        """A report with every scan it can be tied to: its own, and any whose request id is in the trail."""
        with self._connect() as conn:
            rep = conn.execute("SELECT * FROM problem_reports WHERE id = %s", (problem_id,)).fetchone()
            if rep is None:
                return None
            rids = {e.get("request_id") for e in rep["events"] if isinstance(e, dict)} - {None}
            if rep["request_id"]:
                rids.add(rep["request_id"])
            scans = conn.execute(
                """SELECT s.*, p.barcode FROM scans s
                     LEFT JOIN product_versions v ON v.id = s.product_version_id
                     LEFT JOIN products p ON p.id = v.product_id
                    WHERE s.id = %s OR s.request_id = ANY(%s)
                    ORDER BY s.created_at""", (rep["scan_id"], list(rids))).fetchall()
            return {"report": rep, "scans": scans}

    def open_problems(self, limit=50):
        with self._connect() as conn:
            return conn.execute(
                """SELECT id, kind, created_at, signature, comment, scan_id, request_id, app_version, build
                     FROM problem_reports WHERE status = 'open' ORDER BY created_at DESC LIMIT %s""",
                (limit,)).fetchall()

    def set_problem_status(self, problem_id, status, note=None):
        with self._connect() as conn:
            return conn.execute(
                "UPDATE problem_reports SET status = %s, note = coalesce(%s, note) WHERE id = %s RETURNING id",
                (status, note, problem_id)).fetchone() is not None

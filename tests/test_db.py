"""
Database rules (migrations/001_core.sql) against a real Postgres (19 locally, D-087).

Runs on a fresh database per module (conftest.py): embedded Postgres by
default, or the server in INSIDELABEL_TEST_PG.
"""
import pytest

psycopg = pytest.importorskip("psycopg")

from insidelabel.db import migrate  # noqa: E402


@pytest.fixture(scope="module")
def migrated(fresh_db):
    return fresh_db             # (uri, applied, skipped) — see conftest.py


@pytest.fixture
def conn(migrated):
    with psycopg.connect(migrated[0]) as c:
        yield c
        c.rollback()


def product_version(c, status="pending_review", hash_="h1"):
    pid = c.execute("INSERT INTO products (name) VALUES ('Test biscuit') RETURNING id").fetchone()[0]
    vid = c.execute(
        """INSERT INTO product_versions
             (product_id, version_no, ingredient_lines, ingredients, ingredients_hash,
              engine_version, source, status)
           VALUES (%s, 1, '["Wheat flour, Sugar"]', '["Wheat flour", "Sugar"]', %s, '0.1', 'scan', %s)
           RETURNING id""", (pid, hash_, status)).fetchone()[0]
    return pid, vid


def add_version(c, pid, n, hash_):
    return c.execute(
        """INSERT INTO product_versions
             (product_id, version_no, ingredient_lines, ingredients, ingredients_hash, engine_version, source)
           VALUES (%s, %s, '[]', '[]', %s, '0.1', 'scan') RETURNING id""", (pid, n, hash_)).fetchone()[0]


# ---------------------------------------------------------------- migrations

def test_migrations_apply_and_are_idempotent(migrated):
    uri, applied, skipped = migrated
    assert "001_core.sql" in applied
    again, _ = migrate.apply(uri, skip_unavailable=bool(skipped))
    assert again == []                      # nothing reapplied
    if skipped:
        assert skipped == ["002_trigram_search.sql"]


# ---------------------------------------------------------------- D-043

def test_finding_without_evidence_cannot_commit(migrated):
    with psycopg.connect(migrated[0]) as c:
        _, vid = product_version(c)
        c.execute("""INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                           severity, rendered_text, engine_version)
                     VALUES (%s, 'R2-NO-PRESERVATIVE', '1', 'R2', 'fact', 'moderate', 'x', '0.1')""", (vid,))
        with pytest.raises(psycopg.errors.RaiseException, match="has no evidence"):
            c.commit()


def test_finding_with_evidence_commits(migrated):
    with psycopg.connect(migrated[0]) as c:
        _, vid = product_version(c)
        fid = c.execute("""INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                                 severity, rendered_text, engine_version)
                           VALUES (%s, 'R3-NOVA', '1', 'R3', 'fact', 'info', 'x', '0.1') RETURNING id""",
                        (vid,)).fetchone()[0]
        eid = c.execute("""INSERT INTO evidence (product_version_id, kind, pointer, quoted_text)
                           VALUES (%s, 'ingredient', '{"ingredient_position": 2}', 'Invert syrup')
                           RETURNING id""", (vid,)).fetchone()[0]
        c.execute("INSERT INTO finding_evidence VALUES (%s, %s)", (fid, eid))
        c.commit()
        # removing the last evidence row is blocked too
        c.execute("DELETE FROM finding_evidence WHERE finding_id = %s", (fid,))
        with pytest.raises(psycopg.errors.RaiseException, match="has no evidence"):
            c.commit()


def test_evidence_must_be_same_product_version(migrated):
    with psycopg.connect(migrated[0]) as c:
        _, v1 = product_version(c, hash_="a")
        _, v2 = product_version(c, hash_="b")
        fid = c.execute("""INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                                 severity, rendered_text, engine_version)
                           VALUES (%s, 'R3', '1', 'R3', 'fact', 'info', 'x', '0.1') RETURNING id""",
                        (v1,)).fetchone()[0]
        eid = c.execute("""INSERT INTO evidence (product_version_id, kind, pointer)
                           VALUES (%s, 'ingredient', '{}') RETURNING id""", (v2,)).fetchone()[0]
        c.execute("INSERT INTO finding_evidence VALUES (%s, %s)", (fid, eid))
        with pytest.raises(psycopg.errors.RaiseException, match="another product version"):
            c.commit()


# ---------------------------------------------------------------- D-045

def test_finding_cannot_cite_unknown_document(conn):
    _, vid = product_version(conn)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("""INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                              severity, rendered_text, citation_key, engine_version)
                        VALUES (%s, 'R2', '1', 'R2', 'fact', 'x', 'x', 'NOT_A_DOC', '0.1')""", (vid,))


def test_citation_needs_verification_date(conn):
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute("INSERT INTO citations (key, title, url) VALUES ('X', 't', 'u')")


def test_stale_citation_hidden_from_consumers(migrated):
    with psycopg.connect(migrated[0]) as c:
        _, vid = product_version(c)
        c.execute("""INSERT INTO citations (key, title, url, verified_at) VALUES
                       ('FRESH', 't', 'u', current_date), ('STALE', 't', 'u', current_date - 800)""")
        ids = {}
        for key in ("FRESH", "STALE"):
            fid = c.execute("""INSERT INTO findings (product_version_id, rule_code, rule_version, tier, kind,
                                                     severity, rendered_text, citation_key, engine_version)
                               VALUES (%s, 'R2', '1', 'R2', 'fact', 'x', 'x', %s, '0.1') RETURNING id""",
                            (vid, key)).fetchone()[0]
            eid = c.execute("""INSERT INTO evidence (product_version_id, kind, pointer)
                               VALUES (%s, 'citation', '{}') RETURNING id""", (vid,)).fetchone()[0]
            c.execute("INSERT INTO finding_evidence VALUES (%s, %s)", (fid, eid))
            ids[key] = fid
        visible = {r[0] for r in c.execute("SELECT id FROM consumer_findings WHERE product_version_id = %s", (vid,))}
        assert ids["FRESH"] in visible and ids["STALE"] not in visible
        c.rollback()


# ---------------------------------------------------------------- D-026 / D-028

def test_pending_version_cannot_be_current(conn):
    _, vid = product_version(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE product_versions SET is_current = true WHERE id = %s", (vid,))


def test_publish_keeps_one_current_version(conn):
    pid, v1 = product_version(conn, hash_="old")
    conn.execute("SELECT publish_version(%s, 'sushil')", (v1,))
    v2 = add_version(conn, pid, 2, "new")               # reformulation
    conn.execute("SELECT publish_version(%s, 'sushil')", (v2,))
    rows = conn.execute("""SELECT id, is_current, valid_to IS NOT NULL, status
                             FROM product_versions WHERE product_id = %s ORDER BY version_no""",
                        (pid,)).fetchall()
    assert rows == [(v1, False, True, "published"), (v2, True, False, "published")]


def test_two_current_versions_are_impossible(conn):
    pid, v1 = product_version(conn)
    conn.execute("SELECT publish_version(%s, 'r')", (v1,))
    v2 = add_version(conn, pid, 2, "x")
    conn.execute("UPDATE product_versions SET status='published', verified_at=now() WHERE id=%s", (v2,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("UPDATE product_versions SET is_current = true WHERE id = %s", (v2,))


# ---------------------------------------------------------------- D-074

def test_at_most_three_profiles(conn):
    uid = conn.execute("INSERT INTO users DEFAULT VALUES RETURNING id").fetchone()[0]
    for band in ("adult", "kid", "toddler"):
        conn.execute("INSERT INTO user_profiles (user_id, age_band, consent_at) VALUES (%s, %s, now())",
                     (uid, band))
    with pytest.raises(psycopg.errors.RaiseException, match="at most 3"):
        conn.execute("INSERT INTO user_profiles (user_id, age_band, consent_at) VALUES (%s, 'kid', now())",
                     (uid,))


def test_profile_has_no_name_column_and_needs_consent(conn):
    cols = {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'user_profiles'")}
    assert not cols & {"name", "nickname", "dob", "date_of_birth", "email", "phone"}
    uid = conn.execute("INSERT INTO users DEFAULT VALUES RETURNING id").fetchone()[0]
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute("INSERT INTO user_profiles (user_id, age_band) VALUES (%s, 'kid')", (uid,))


# ---------------------------------------------------------------- scans & review queue

def test_verdict_scan_needs_a_version(conn):
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute("INSERT INTO scans (resolved_via, outcome) VALUES ('new_product', 'verdict')")
    conn.execute("INSERT INTO scans (resolved_via, outcome, error_code) VALUES ('failed', 'refused', 'back_not_read')")


def test_review_queue_hands_each_item_to_one_reviewer(migrated):
    uri = migrated[0]
    with psycopg.connect(uri) as setup:
        setup.execute("DELETE FROM review_queue")
        sid = setup.execute("INSERT INTO scans (resolved_via, outcome) VALUES ('failed', 'refused') RETURNING id").fetchone()[0]
        for _ in range(2):
            setup.execute("INSERT INTO review_queue (kind, scan_id) VALUES ('send_to_us', %s)", (sid,))
        setup.commit()
    # Two reviewers claim concurrently, each inside an open transaction.
    with psycopg.connect(uri) as a, psycopg.connect(uri) as b:
        ra = a.execute("SELECT id FROM claim_next_review('reviewer-a')").fetchone()
        rb = b.execute("SELECT id FROM claim_next_review('reviewer-b')").fetchone()
        assert ra and rb and ra != rb
        a.commit(); b.commit()
    with psycopg.connect(uri) as c:
        assert c.execute("SELECT id FROM claim_next_review('reviewer-c')").fetchone() is None

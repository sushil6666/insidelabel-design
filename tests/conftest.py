"""
Shared Postgres fixtures.

Each test module that asks for `fresh_db` gets its own newly created, fully
migrated database, dropped afterwards. Where it runs:

  * INSIDELABEL_TEST_PG set -> on that server. The URI must name a *_test
    database; it is only used to create and drop siblings of it
    (<name>_<random>), never written to itself.
  * otherwise -> an embedded Postgres from pgserver (no install needed; it
    lacks pg_trgm, so 002 is skipped there).
"""
import os
import uuid

import pytest

# D-101: most API tests send a recorded model answer as `replay`. The server
# refuses it unless this is on; test_replay_gate.py checks the refusal.
os.environ.setdefault("INSIDELABEL_ALLOW_REPLAY", "on")

# api/main.py stores every scan in INSIDELABEL_DB when it is set, at import. A suite
# run from a shell that has it (`INSIDELABEL_DB=... release_check.py --with-tests`)
# wrote 386 scans, 52 users and 5 problem reports into the laptop's real database
# (2026-09-28). Tests get their databases from fresh_db only.
os.environ.pop("INSIDELABEL_DB", None)

# The same for the paid readers: a shell with GOOGLE_VISION_KEY set made every test
# that posts a photo without cloud_vision.replaying() send its fake image to Google
# ("Cloud Vision error: Bad image data", found 2026-09-30 with D-139). Tests that need
# a key set a fake one and stand in for Google themselves (test_cloud_vision.py).
os.environ.pop("GOOGLE_VISION_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """D-095 counters are per process: the suite makes hundreds of scans from one 'IP'."""
    from insidelabel import ratelimit
    ratelimit.LIMITER.reset()
    yield


@pytest.fixture(autouse=True)
def _fresh_vision_cache():
    """Cloud Vision keeps the text it read per photo hash, and every test sends the
    same 1x1 PNG, so one test's text leaked into the next: an unlisted scan's replay
    in test_no_barcode.py read as cross-checked or not depending on which test ran
    before it (found 2026-09-29, when a new test file changed the order)."""
    from insidelabel.extraction.providers import cloud_vision
    cloud_vision._CACHE.clear()
    yield


@pytest.fixture(scope="session")
def pg_admin():
    """(admin_uri, base_name, skip_unavailable) for the server tests run on."""
    psycopg = pytest.importorskip("psycopg")
    external = os.environ.get("INSIDELABEL_TEST_PG")
    if external:
        with psycopg.connect(external) as c:
            db = c.execute("SELECT current_database()").fetchone()[0]
        if not db.endswith("_test"):
            pytest.exit(f"INSIDELABEL_TEST_PG points at {db!r}; tests only run on a *_test database")
        yield external, db, False
        return
    pgserver = pytest.importorskip("pgserver")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        srv = pgserver.get_server(d, cleanup_mode="stop")
        yield srv.get_uri(), "il_test", True


@pytest.fixture(scope="module")
def fresh_db(pg_admin):
    """(uri, applied, skipped) for a new migrated database, dropped after the module."""
    import psycopg
    from psycopg.conninfo import make_conninfo

    from insidelabel.db import migrate

    admin, base, skip = pg_admin
    name = f"{base}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    uri = make_conninfo(admin, dbname=name)
    try:
        applied, skipped = migrate.apply(uri, skip_unavailable=skip)
        yield uri, applied, skipped
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

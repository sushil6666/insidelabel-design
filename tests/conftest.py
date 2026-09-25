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

"""
Plain-SQL migration runner. Applies migrations/NNN_*.sql in order, once each,
recording them in schema_migrations. Each file runs in its own transaction.

A file whose first line is `-- requires-extension: <name>` needs that
extension. On a server that lacks it the file fails, unless
skip_unavailable=True (the embedded test server): then it is skipped and NOT
recorded, so it applies later on a full install.

After the migrations it syncs reference data (FSSAI food categories from
data/food_categories.json) — idempotent, so it runs every time.

    python -m insidelabel.db.migrate postgresql://...
"""

import os
import re
import sys

import psycopg

MIGRATIONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "migrations"))

_REQUIRES = re.compile(r"^--\s*requires-extension:\s*(\w+)")


def _files():
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if re.match(r"^\d{3}_.*\.sql$", f))


def apply(conninfo, skip_unavailable=False):
    """Apply pending migrations. Returns (applied, skipped) lists of filenames."""
    applied, skipped = [], []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                          filename text PRIMARY KEY,
                          applied_at timestamptz NOT NULL DEFAULT now())""")
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        available = {r[0] for r in conn.execute("SELECT name FROM pg_available_extensions")}

        for name in _files():
            if name in done:
                continue
            with open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8") as f:
                sql = f.read()
            m = _REQUIRES.match(sql)
            if m and m.group(1) not in available and skip_unavailable:
                skipped.append(name)
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (name,))
            applied.append(name)
        # Reference data that tables point at: FSSAI food categories.
        from insidelabel.db import categories
        with conn.transaction():
            categories.sync(conn)
    return applied, skipped


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m insidelabel.db.migrate <postgres-uri>")
    a, s = apply(sys.argv[1])
    print("applied:", ", ".join(a) or "nothing new")
    if s:
        print("skipped:", ", ".join(s))

#!/usr/bin/env python3
"""
Which stored versions change kind of pack under today's rule (D-092, D-187).

Every scan's version keeps the model's raw answer (raw_extraction) and the kind
core/pack_kind.decide() gave it then (pack_kind). D-187 changed the licence rule
(item #82: a plain "Lic No." made a vermicelli pack not_food), so this replays
decide() on each stored answer, as /scan calls it (no category), and lists every
version whose kind or reviewer notes come out different. It also shows what the
review checker now sees with the product's category. Read-only: no model call,
nothing written; a changed version is fixed by its review, not by this tool.

    INSIDELABEL_DB=... python tools/pack_kind_replay.py
    il tools/pack_kind_replay.py                    # on the server
    il tools/pack_kind_replay.py --all              # unchanged versions listed too
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.core import pack_kind  # noqa: E402

VERSIONS = """
SELECT v.id, v.status, v.pack_kind, v.pack_kind_evidence, v.raw_extraction,
       p.barcode, p.name, k.code AS category_code,
       (SELECT string_agg(q.id::text || ' ' || q.status, ', ' ORDER BY q.id)
          FROM review_queue q WHERE q.product_version_id = v.id) AS review_items
  FROM product_versions v
  JOIN products p ON p.id = v.product_id
  LEFT JOIN categories k ON k.id = p.category_id
 WHERE v.raw_extraction IS NOT NULL AND v.pack_kind IS NOT NULL
 ORDER BY v.id
"""


def replay(rows):
    """Each stored version with its stored kind and today's, and whether they differ."""
    out = []
    for r in rows:
        raw = r["raw_extraction"] or {}
        now = pack_kind.decide(raw)
        with_category = pack_kind.decide(raw, category=r["category_code"])
        was_review = (r["pack_kind_evidence"] or {}).get("review") or []
        out.append({**{k: r[k] for k in ("id", "status", "barcode", "name", "category_code", "review_items")},
                    "was": r["pack_kind"], "now": now["code"], "now_review": now["review"],
                    "checker": with_category["code"], "checker_review": with_category["review"],
                    "changed": r["pack_kind"] != now["code"] or was_review != now["review"]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="list unchanged versions too")
    args = ap.parse_args()
    db = os.environ.get("INSIDELABEL_DB")
    if not db:
        sys.exit("INSIDELABEL_DB is not set")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(db, row_factory=dict_row) as conn:
        conn.read_only = True
        rows = conn.execute(VERSIONS).fetchall()
    out = replay(rows)
    changed = [r for r in out if r["changed"]]
    for r in out if args.all else changed:
        print(f"version {r['id']} ({r['status']}) {r['barcode'] or '-'} {r['name'] or ''}: "
              f"{r['was']} -> {r['now']}; review item(s) {r['review_items'] or '-'}")
        for note in r["now_review"]:
            print(f"    now: {note}")
        if r["checker"] != r["now"] or r["checker_review"] != r["now_review"]:
            print(f"    with category {r['category_code']}: {r['checker']}; " + "; ".join(r["checker_review"]))
    print(f"{len(out)} versions replayed, {len(changed)} changed")


if __name__ == "__main__":
    main()

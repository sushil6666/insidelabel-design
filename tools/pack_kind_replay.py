#!/usr/bin/env python3
"""
Which stored versions change kind of pack under today's rule (D-092, D-187).

Every scan's version keeps the model's raw answer (raw_extraction) and the kind
core/pack_kind.decide() gave it then (pack_kind). D-187 changed the licence rule
(item #82: a plain "Lic No." made a vermicelli pack not_food), so this replays
decide() on each stored answer, as /scan calls it (no category), and lists every
version whose kind or reviewer notes come out different. It also shows what the
review checker now sees with the product's category. No model call. By default
nothing is written.

D-188: --apply --by <name> writes today's kind on each changed version: pack_kind
and pack_kind_evidence (today's evidence and review notes, plus a note naming the
decision, the old and new kind, the date and who ran it), and nothing else on the
version.

Each written row is printed. Version 74 (item #82) was fixed by hand on 2026-10-08
before this existed (D-187's follow-up line).

D-190: the notes are a list, `corrections`, oldest first. --apply appends its note and
keeps every earlier one, including an old single `corrected` string (D-188's form) as
the first entry: on 2026-10-08 the single string replaced the manual note on version 74.

    INSIDELABEL_DB=... python tools/pack_kind_replay.py
    il tools/pack_kind_replay.py                    # on the server
    il tools/pack_kind_replay.py --all              # unchanged versions listed too
    il tools/pack_kind_replay.py --apply --by Sushil --decision D-190
"""
import datetime
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
                    "now_evidence": now["evidence"], "was_evidence": r["pack_kind_evidence"],
                    "checker": with_category["code"], "checker_review": with_category["review"],
                    "changed": r["pack_kind"] != now["code"] or was_review != now["review"]})
    return out


# D-188: only the kind and its evidence; the guard on the old kind skips a row changed meanwhile.
APPLY = """
UPDATE product_versions SET pack_kind = %s, pack_kind_evidence = %s
 WHERE id = %s AND pack_kind = %s
"""


def corrected(r, decision, by, day):
    """The note kept on a corrected version: which rule, old and new kind, who, when."""
    return (f"{decision}: was {r['was']}; pack_kind_replay gives {r['now']}. "
            f"Applied with --apply by {by}, {day}")


def corrections(stored):
    """D-190: the notes already on a version, oldest first: its `corrections` list, after
    an old single `corrected` string (D-188's form) when there is one."""
    stored = stored or {}
    old = [stored["corrected"]] if stored.get("corrected") else []
    return old + [n for n in stored.get("corrections") or [] if n not in old]


def apply(conn, changed, decision, by, day=None):
    """Write today's kind and evidence on each changed version, keeping its earlier
    notes (D-190). Returns the rows written."""
    from psycopg.types.json import Jsonb
    day = day or datetime.date.today().isoformat()
    done = []
    for r in changed:
        evidence = {"evidence": r["now_evidence"], "review": r["now_review"],
                    "corrections": corrections(r.get("was_evidence")) + [corrected(r, decision, by, day)]}
        n = conn.execute(APPLY, (r["now"], Jsonb(evidence), r["id"], r["was"])).rowcount
        if n:
            done.append({**r, "evidence": evidence})
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="list unchanged versions too")
    ap.add_argument("--apply", action="store_true",
                    help="write today's kind and evidence on each changed version (default: read-only)")
    ap.add_argument("--by", help="who ran --apply (required with --apply)")
    ap.add_argument("--decision", default="D-187", help="the rule the replay follows (default D-187)")
    args = ap.parse_args()
    if args.apply and not (args.by or "").strip():
        sys.exit("--apply needs --by <name>")
    db = os.environ.get("INSIDELABEL_DB")
    if not db:
        sys.exit("INSIDELABEL_DB is not set")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(db, row_factory=dict_row) as conn:
        conn.read_only = not args.apply
        rows = conn.execute(VERSIONS).fetchall()
        out = replay(rows)
        changed = [r for r in out if r["changed"]]
        written = apply(conn, changed, args.decision, args.by.strip()) if args.apply else []
    for r in out if args.all else changed:
        print(f"version {r['id']} ({r['status']}) {r['barcode'] or '-'} {r['name'] or ''}: "
              f"{r['was']} -> {r['now']}; review item(s) {r['review_items'] or '-'}")
        for note in r["now_review"]:
            print(f"    now: {note}")
        if r["checker"] != r["now"] or r["checker_review"] != r["now_review"]:
            print(f"    with category {r['category_code']}: {r['checker']}; " + "; ".join(r["checker_review"]))
    for r in written:
        print(f"written: version {r['id']}: pack_kind {r['was']} -> {r['now']}; corrected: {r['evidence']['corrections'][-1]}")
    print(f"{len(out)} versions replayed, {len(changed)} changed"
          + (f", {len(written)} written" if args.apply else ", nothing written"))


if __name__ == "__main__":
    main()

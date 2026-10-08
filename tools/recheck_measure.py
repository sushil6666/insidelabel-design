#!/usr/bin/env python3
"""
How often D-175's free re-check would say "unchanged" on the packs we have published.

    INSIDELABEL_DB=... python tools/recheck_measure.py            # counts and one line per pack
    il tools/recheck_measure.py                                   # on the server (DEPLOY.md)

Why: the free comparison (review/checker.unchanged) was measured on the four real
Cloud Vision texts the repo keeps (2026-10-08). The server has the real ones: each
published version, and the Cloud Vision text of the scans that read it. This replays
the rule on each pair with no model call and no Google call (the text is stored on the
scan, D-092), and says how often a re-check photo would skip the paid read, and why the
rest wouldn't. A pack that prints entries without commas between them fails the entry
count every time, and pays about Rs 0.6 each time it is checked: this shows how many do.

Read-only. Prints product names and the checks that failed; no user, device or photo.
"""
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from insidelabel.review import checker  # noqa: E402

# The latest scan per published version whose back Cloud Vision read, with the same list.
PAIRS = """
SELECT DISTINCT ON (v.id) v.id, p.name, v.ingredients, v.allergen_statement, s.ocr->'back'->>'text' AS text
  FROM product_versions v
  JOIN products p ON p.id = v.product_id
  JOIN scans s ON s.product_version_id = v.id
 WHERE v.is_current AND s.ocr->'back'->>'reader' = 'cloud_vision'
   AND coalesce(s.ocr->'back'->>'text', '') <> ''
 ORDER BY v.id, s.created_at DESC
"""

REASONS = ("missing", "lost", "lost_ins", "new_allergens", "out_of_order")


def why(r):
    """The checks that kept a pack from "unchanged", in words a reader can scan."""
    out = []
    if not r["section_found"]:
        out.append("no list found")
    elif not r["list_end_found"]:
        out.append("list end not found")
    out += [f"{k} {', '.join(map(str, r[k][:6]))}" for k in REASONS if r[k]]
    if r["entries"] != r["stored_entries"]:
        out.append(f"entries {r['entries']} vs {r['stored_entries']}")
    return "; ".join(out)


def main():
    uri = os.environ.get("INSIDELABEL_DB")
    if not uri:
        sys.exit("set INSIDELABEL_DB")
    with psycopg.connect(uri, row_factory=dict_row) as conn:
        rows = conn.execute(PAIRS).fetchall()
    if not rows:
        print("No published version has a stored Cloud Vision text yet: nothing to measure (TODO).")
        return
    tally = collections.Counter()
    for row in rows:
        r = checker.unchanged(row["ingredients"], row["allergen_statement"], row["text"])
        tally[r["decision"]] += 1
        for k in REASONS:
            tally[k] += bool(r[k])
        tally["entry_count"] += r["entries"] != r["stored_entries"]
        print(f"{r['decision']:9}  {row['name'][:40]:40}  {why(r)}")
    n = len(rows)
    print(f"\n{tally['unchanged']} of {n} published packs would pass as unchanged for free; "
          f"{tally['not_clear']} would go to the paid read.")
    print("Why not: " + ", ".join(f"{k} {tally[k]}" for k in (*REASONS, "entry_count") if tally[k]))


if __name__ == "__main__":
    main()

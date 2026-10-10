#!/usr/bin/env python3
"""
D-191: how the free table hint (INSIDELABEL_TABLE_HINT) would have done on real photos.

The hint is off until these numbers are accepted (Sushil, 2026-10-10). This runs the same
check /check-photo would (insidelabel/table_hint.py: one local Tesseract pass, the word
lists in data/table_hint.json) on the stored back photo of every photo scan of the last
30 days that sent one back photo (a joined photo holds a table on purpose, D-119, D-171),
and prints:

  false alarms  it fires on a scan that gave a result (the list was there and read)
  catches       it fires on a `no_ingredient_list_found` scan whose nutrition table Gemini
                read (status read or partial): the retakes it is meant to save
  misses        it doesn't fire on such a scan
  time          per photo, median and slowest tenth, and how many went past the 3 s cap

Read-only: nothing is written, no Gemini or Cloud Vision call (Tesseract runs here, free).

    INSIDELABEL_DB=... INSIDELABEL_MEDIA=... python tools/table_hint_measure.py
    il tools/table_hint_measure.py --days 30
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

SCANS = """
SELECT id, outcome, error_code, back_image_key, model_raw FROM scans
 WHERE created_at > now() - make_interval(days => %s) AND back_image_key IS NOT NULL
   AND photos_deleted_at IS NULL AND NOT cache_hit
   AND COALESCE((request->>'back_parts')::int, 1) = 1
   AND COALESCE((request->>'table_only')::boolean, false) = false
 ORDER BY created_at
"""


def table_read(model_raw):
    """Did Gemini read a nutrition table in this answer (read or partial)?"""
    try:
        return (json.loads(model_raw or "{}").get("nutrition") or {}).get("status") in ("read", "partial")
    except (ValueError, AttributeError):
        return False


def measure(rows, photo_of, check):
    """Count false alarms, catches and misses, with each check's ms."""
    out = {"result": 0, "false_alarms": [], "table_only": 0, "catches": [], "misses": [], "ms": [], "no_photo": 0}
    for r in rows:
        kind = ("result" if r["outcome"] in ("verdict", "unlisted")
                else "table_only" if r["error_code"] == "no_ingredient_list_found" and table_read(r["model_raw"])
                else None)
        if kind is None:
            continue
        photo = photo_of(r["back_image_key"])
        if photo is None:
            out["no_photo"] += 1
            continue
        got = check(photo)
        out["ms"].append(got["ms"])
        out[kind] += 1
        if kind == "result" and got["fires"]:
            out["false_alarms"].append(r["id"])
        elif kind == "table_only":
            out["catches" if got["fires"] else "misses"].append(r["id"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    db = os.environ.get("INSIDELABEL_DB")
    if not db:
        sys.exit("INSIDELABEL_DB is not set")
    import psycopg
    from psycopg.rows import dict_row

    from insidelabel import table_hint
    from insidelabel.media import LocalMedia

    if not table_hint.AVAILABLE:
        sys.exit("Tesseract (pytesseract) is not installed here.")
    media = LocalMedia(os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    with psycopg.connect(db, row_factory=dict_row) as conn:
        conn.read_only = True
        rows = conn.execute(SCANS, (args.days,)).fetchall()
    got = measure(rows, lambda key: (media.get(key) or (None,))[0], table_hint.check)
    ms = sorted(got["ms"])
    print(f"Last {args.days} days, one back photo each ({got['no_photo']} photos no longer stored):")
    print(f"  false alarms: {len(got['false_alarms'])} of {got['result']} scans that gave a result"
          + (f" (scans {', '.join(str(i) for i in got['false_alarms'][:20])})" if got["false_alarms"] else ""))
    print(f"  catches:      {len(got['catches'])} of {got['table_only']} 'no ingredient list' scans with a table read"
          + (f" (scans {', '.join(str(i) for i in got['catches'][:20])})" if got["catches"] else ""))
    print(f"  misses:       {len(got['misses'])}")
    if ms:
        print(f"  time:         median {ms[len(ms) // 2]} ms, slowest tenth from {ms[int(len(ms) * 0.9)]} ms, "
              f"{sum(1 for m in ms if m >= table_hint.READ_CAP_S * 1000)} at the {table_hint.READ_CAP_S:.0f} s cap")


if __name__ == "__main__":
    main()

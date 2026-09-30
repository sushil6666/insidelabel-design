#!/usr/bin/env python3
"""
D-141 before it ships: the old rule (one read) and the new rule (two reads that
agree) over photos the server already holds. Read-only: no Gemini, no Cloud
Vision, nothing written; zxing-cpp only, as /check-photo runs it.

What the server holds: /check-photo stores nothing (D-104), so a barcode photo
taken on its own is never kept. The photos kept are scan photos (back, front)
in the media store, and a barcode on them is read by the same function
("Barcode ... found on it too"), which D-141 point 3 puts under the same rule.
So this measures read_from_photo() on every stored photo; --dir adds any other
folder (Sushil's own barcode photos, gold/).

With INSIDELABEL_DB set, each photo whose read changes is shown with the
barcode its scan recorded and where that came from (camera scanner or photo),
so a refusal can be told apart: the old read matched the pack, or it didn't.

    INSIDELABEL_MEDIA=… INSIDELABEL_DB=… python tools/barcode_reads.py
    python tools/barcode_reads.py --no-media --dir <folder of photos>
    il tools/barcode_reads.py                    # on the server (OPERATIONS.md)

The line D-141 was accepted with (Sushil, 2026-09-30): if the new rule refuses
more than 5% of the photos the old rule accepted, stop and report.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel import barcode  # noqa: E402

LINE = 5.0                                   # per cent, D-141 as accepted
PHOTO = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


def photos(dirs):
    for d in dirs:
        for base, _sub, files in os.walk(d):
            for f in sorted(files):
                if f.lower().endswith(PHOTO):
                    yield os.path.join(base, f)


def scans_for(db, keys):
    """{photo key: [(barcode, barcode_source)]} from the scans that used it. Read-only."""
    if not db or not keys:
        return {}
    import psycopg
    out = {}
    with psycopg.connect(db) as conn:
        conn.read_only = True
        rows = conn.execute(
            """SELECT k.key, s.request->>'barcode', s.request->>'barcode_source'
                 FROM scans s
                 CROSS JOIN LATERAL (VALUES (s.back_image_key), (s.front_image_key)) AS k(key)
                WHERE k.key = ANY(%s)""", (list(keys),)).fetchall()
    for key, code, source in rows:
        if code:
            out.setdefault(key, set()).add((code, source or "unknown"))
    return out


def measure(paths):
    rows, unreadable, second_ms = [], 0, []
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        old, old_bad = barcode.read_from_photo(data, two_reads=False)
        t0 = time.perf_counter()
        new, new_bad = barcode.read_from_photo(data)
        if old:
            second_ms.append((time.perf_counter() - t0) * 1000)
        if not old and not old_bad and not new:
            try:
                from PIL import Image
                Image.open(p).verify()
            except Exception:                    # noqa: BLE001 - HEIC or a broken file: nothing read either way
                unreadable += 1
        rows.append({"path": p, "old": old, "new": new, "unsure": "barcode_unsure" in new_bad})
    return rows, unreadable, second_ms


def report(rows, unreadable, second_ms, recorded, out=print):
    accepted_old = [r for r in rows if r["old"]]
    accepted_new = [r for r in rows if r["new"]]
    refused = [r for r in accepted_old if not r["new"]]
    differ = [r for r in rows if r["old"] != r["new"]]
    out(f"photos read: {len(rows)} ({unreadable} not readable here, e.g. HEIC)")
    out(f"old rule (one read):       {len(accepted_old)} photo(s) with a barcode accepted, "
        f"{sum(len(r['old']) for r in rows)} code(s)")
    out(f"new rule (two reads agree): {len(accepted_new)} photo(s) with a barcode accepted, "
        f"{sum(len(r['new']) for r in rows)} code(s)")
    if second_ms:
        out(f"second read: {sum(second_ms) / len(second_ms):.0f} ms on average (both reads, per photo with a code)")
    out(f"codes differ on {len(differ)} photo(s):")
    for r in differ:
        name = os.path.basename(r["path"])
        lost = [c for c in r["old"] if c not in r["new"]]
        line = f"  {name}: old {','.join(r['old']) or '-'}  new {','.join(r['new']) or '-'}  refused {','.join(lost)}"
        seen = recorded.get(name)
        if seen:
            line += "  scan recorded " + "; ".join(f"{c} ({s})" for c, s in sorted(seen))
        out(line)
    pct = 100.0 * len(refused) / len(accepted_old) if accepted_old else 0.0
    out(f"refused by the new rule, accepted by the old: {len(refused)} of {len(accepted_old)} ({pct:.1f}%)")
    if not accepted_old:
        out("no photo had a barcode the old rule accepted: nothing measured (TODO, not a pass)")
        return None
    out(f"D-141 line ({LINE:.0f}%): {'ABOVE - stop and report' if pct > LINE else 'within'}")
    return pct


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")),
                    help="the photo store (default: INSIDELABEL_MEDIA)")
    ap.add_argument("--no-media", action="store_true", help="only the --dir folders")
    ap.add_argument("--dir", action="append", default=[], help="another folder of photos (repeatable)")
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"),
                    help="to show what each changed photo's scan recorded (read-only)")
    a = ap.parse_args(argv)
    dirs = ([] if a.no_media else [a.media]) + a.dir
    for d in dirs:
        if not os.path.isdir(d):
            sys.exit(f"no folder at {d}")
    rows, unreadable, second_ms = measure(photos(dirs))
    changed = {os.path.basename(r["path"]) for r in rows if r["old"] != r["new"]}
    try:
        recorded = scans_for(a.db, changed)
    except Exception as e:                       # noqa: BLE001 - the counts don't need the database
        print(f"(database not read: {e})")
        recorded = {}
    report(rows, unreadable, second_ms, recorded)


if __name__ == "__main__":
    main()

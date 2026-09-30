#!/usr/bin/env python3
"""
D-144 before it ships: the old rule (one read) and the new rule (two reads agree,
or the code's digits are in that photo's OCR text) over photos the server holds.
Read-only: no Gemini, no Cloud Vision call, nothing written.

What the server holds: /check-photo stores nothing (D-104), so a barcode photo
taken on its own is never kept. The photos kept are scan photos (back, front) in
the media store. The OCR text is the one /scan read and stored on the scan row
(Cloud Vision, migration 007), for the back photo only, as /scan uses it. A back
photo whose scan kept no text (a Tesseract read keeps only its reader) is read
with Tesseract here, locally and free, but only where the text decides the
answer (--no-tesseract to skip: those then count on two reads alone). A front
photo has no OCR text at /scan, so two reads decide it.

With INSIDELABEL_DB set, each photo whose read changes is shown with the barcode
its scan recorded and where that came from (camera scanner or photo), so a
refusal can be told apart: the old read matched the pack, or it didn't. Without
the database there is no OCR text, and the new rule is two reads only.

    INSIDELABEL_MEDIA=... INSIDELABEL_DB=... python tools/barcode_reads.py
    python tools/barcode_reads.py --no-media --dir <folder of photos>
    il tools/barcode_reads.py                    # on the server (OPERATIONS.md)

The line (Sushil, 2026-09-30): if the new rule refuses more than 5% of the photos
the old rule accepted, stop and report.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel import barcode  # noqa: E402

LINE = 5.0                                   # per cent
PHOTO = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


def photos(dirs):
    for d in dirs:
        for base, _sub, files in os.walk(d):
            for f in sorted(files):
                if f.lower().endswith(PHOTO):
                    yield os.path.join(base, f)


def from_db(db):
    """
    ({back photo key: stored OCR text or None}, {photo key: {(barcode, source)}}), read-only.
    Every key that is some scan's back photo is in the first, text or not.
    """
    if not db:
        return {}, {}
    import psycopg
    backs, sent = {}, {}
    with psycopg.connect(db) as conn:
        conn.read_only = True
        for key, text in conn.execute(
                """SELECT back_image_key, ocr->'back'->>'text' FROM scans WHERE back_image_key IS NOT NULL"""):
            backs[key] = backs.get(key) or text
        for key, code, source in conn.execute(
                """SELECT k.key, s.request->>'barcode', s.request->>'barcode_source'
                     FROM scans s CROSS JOIN LATERAL (VALUES (s.back_image_key), (s.front_image_key)) AS k(key)
                    WHERE k.key IS NOT NULL AND s.request->>'barcode' IS NOT NULL"""):
            sent.setdefault(key, set()).add((code, source or "unknown"))
    return backs, sent


def tesseract_text(data):
    """Tesseract's text of a photo (local, free), or None where it isn't installed."""
    from insidelabel.extraction.providers import ocr_check
    return ocr_check.read_text(data) if ocr_check.AVAILABLE else None


def measure(paths, backs=None, tesseract=True, ocr=tesseract_text):
    backs = backs or {}
    rows, unreadable, ms = [], 0, []
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        key = os.path.basename(p)
        old, old_bad = barcode.read_from_photo(data, two_reads=False)
        t0 = time.perf_counter()
        two, _ = barcode.read_from_photo(data)                       # two reads, no OCR text
        if old:
            ms.append((time.perf_counter() - t0) * 1000)
        text, text_from = backs.get(key), "cloud_vision"
        if key in backs and not text and tesseract and any(c not in two for c in old):
            text, text_from = ocr(data), "tesseract"                   # only where it decides the answer
        new = barcode.read_from_photo(data, ocr_text=text)[0] if text else two
        if not old and not old_bad:
            try:
                from PIL import Image
                Image.open(p).verify()
            except Exception:                    # noqa: BLE001 - HEIC or a broken file: nothing read either way
                unreadable += 1
        rows.append({"path": p, "old": old, "new": new, "two_reads": two,
                     "by_ocr": [c for c in new if c not in two], "ocr_from": text_from if text else None})
    return rows, unreadable, ms


def report(rows, unreadable, ms, recorded, out=print):
    accepted_old = [r for r in rows if r["old"]]
    accepted_new = [r for r in rows if r["new"]]
    refused = [r for r in accepted_old if not r["new"]]
    differ = [r for r in rows if r["old"] != r["new"]]
    saved = [r for r in rows if r["by_ocr"]]
    out(f"photos read: {len(rows)} ({unreadable} not readable here, e.g. HEIC)")
    out(f"old rule (one read):                   {len(accepted_old)} photo(s) with a barcode accepted, "
        f"{sum(len(r['old']) for r in rows)} code(s)")
    out(f"new rule (two reads agree, or OCR):    {len(accepted_new)} photo(s) with a barcode accepted, "
        f"{sum(len(r['new']) for r in rows)} code(s); {len(saved)} of them by the OCR text only")
    if ms:
        out(f"two reads: {sum(ms) / len(ms):.0f} ms on average per photo with a code")
    out(f"codes differ on {len(differ)} photo(s):")
    for r in differ:
        name = os.path.basename(r["path"])
        lost = [c for c in r["old"] if c not in r["new"]]
        line = (f"  {name}: old {','.join(r['old']) or '-'}  new {','.join(r['new']) or '-'}  "
                f"refused {','.join(lost) or '-'}  OCR text: {r['ocr_from'] or 'none'}")
        seen = recorded.get(name)
        if seen:
            line += "  scan recorded " + "; ".join(f"{c} ({s})" for c, s in sorted(seen))
        out(line)
    for r in saved:
        out(f"  kept by the OCR text ({r['ocr_from']}), second read empty or different: "
            f"{os.path.basename(r['path'])} {','.join(r['by_ocr'])}")
    pct = 100.0 * len(refused) / len(accepted_old) if accepted_old else 0.0
    out(f"refused by the new rule, accepted by the old: {len(refused)} of {len(accepted_old)} ({pct:.1f}%)")
    if not accepted_old:
        out("no photo had a barcode the old rule accepted: nothing measured (TODO, not a pass)")
        return None
    out(f"line ({LINE:.0f}%): {'ABOVE - stop and report' if pct > LINE else 'within'}")
    return pct


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")),
                    help="the photo store (default: INSIDELABEL_MEDIA)")
    ap.add_argument("--no-media", action="store_true", help="only the --dir folders")
    ap.add_argument("--dir", action="append", default=[], help="another folder of photos (repeatable)")
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"),
                    help="the OCR text of each back photo, and what each changed photo's scan recorded (read-only)")
    ap.add_argument("--no-tesseract", action="store_true", help="don't read a back photo that has no stored text")
    a = ap.parse_args(argv)
    dirs = ([] if a.no_media else [a.media]) + a.dir
    for d in dirs:
        if not os.path.isdir(d):
            sys.exit(f"no folder at {d}")
    try:
        backs, recorded = from_db(a.db)
    except Exception as e:                       # noqa: BLE001 - two reads can still be counted
        print(f"(database not read, so no OCR text: {e})")
        backs, recorded = {}, {}
    if not a.db:
        print("(no database: no OCR text, the new rule is two reads only)")
    rows, unreadable, ms = measure(photos(dirs), backs, tesseract=not a.no_tesseract)
    report(rows, unreadable, ms, recorded)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
D-191: which stored clearer-photo requests (D-118) would still ask under today's rule.

Every `independent_read_failed` scan keeps Gemini's raw answer (model_raw) and Cloud
Vision's text of the back (ocr.back.text), so the ask can be re-decided with no call:
Gemini's list is re-read from its stored answer (as a replay does, D-092), and /scan's
own cross_check() runs on it and the stored text, then D-191's one ask per pack per phone
over the scans in order. Each scan is printed with what it asked on (the stored check) and
what today's rule does, and why. Read-only: nothing is written, no model or Vision call.

The list is Gemini's before D-093's recovery (not stored), which only adds INS numbers
already in Cloud Vision's text, so it can only make a missing word rarer, never commoner.

For a missing word, it also says where the word came from: in Gemini's answer, or not
(added later, by D-093's recovery from the reader's text): the "contaadded" question.

    INSIDELABEL_DB=... python tools/cross_check_replay.py
    il tools/cross_check_replay.py --since 2026-10-05
"""
import argparse
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

SCANS = """
SELECT id, created_at, user_id, request, model_raw, ocr FROM scans
 WHERE error_code = 'independent_read_failed' AND created_at >= %s AND model_raw IS NOT NULL
 ORDER BY created_at
"""
DAY = datetime.timedelta(hours=24)


def redecide(rows, cross_check, read_list):
    """Each row: before (always asked), after (asks now?), why, and today's check."""
    asked_at, out = {}, []
    for r in rows:
        back = ((r["ocr"] or {}).get("back") or {})
        before = back.get("independent_read") or {}
        ingredients, statement = read_list(r)
        text = back.get("text") or ""
        if back.get("reader") != "cloud_vision" or not text.strip():
            out.append({**_head(r), "before": before, "after": None, "why": "no stored Cloud Vision text"})
            continue
        matters, check = cross_check(ingredients, statement, text)
        key = (str(r["user_id"]), (r["request"] or {}).get("barcode"))
        why = ("confirmed now" if check is None else "asks: it would change the result" if matters
               else "doesn't change the result")
        if matters and r["user_id"] and key in asked_at and r["created_at"] - asked_at[key] <= DAY:
            matters, why = False, f"already asked for this pack on this phone at {asked_at[key]:%H:%M}"
        if matters:
            asked_at[key] = r["created_at"]
        raw = (r["model_raw"] or "").lower()
        origin = {w: ("in Gemini's answer" if w in raw else "not in Gemini's answer (added by D-093's recovery)")
                  for w in (check or {}).get("missing") or [] if w != "(no text)"}
        out.append({**_head(r), "before": before, "after": bool(matters), "why": why, "check": check,
                    "origin": origin})
    return out


def _head(r):
    return {"id": r["id"], "at": r["created_at"], "barcode": (r["request"] or {}).get("barcode")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-10-05", help="first day (default 2026-10-05, D-159)")
    args = ap.parse_args()
    db = os.environ.get("INSIDELABEL_DB")
    if not db:
        sys.exit("INSIDELABEL_DB is not set")
    import psycopg
    from psycopg.rows import dict_row

    from insidelabel.api import main as api
    from insidelabel.extraction.providers import gemini

    def read_list(r):
        roles = (r["request"] or {}).get("images") or ["back"]
        vision, _c = gemini.analyze_images([(b"", "image/jpeg", role) for role in roles],
                                           raw_response=r["model_raw"])
        return vision.get("ingredients") or [], vision.get("allergen_statement")

    with psycopg.connect(db, row_factory=dict_row) as conn:
        conn.read_only = True
        rows = conn.execute(SCANS, (args.since,)).fetchall()
    out = redecide(rows, api.cross_check, read_list)
    for r in out:
        b = r["before"]
        print(f"scan {r['id']} {r['at']:%Y-%m-%d %H:%M} {r['barcode'] or '-'}: "
              f"{'ASKS' if r['after'] else 'no ask' if r['after'] is False else '?'}: {r['why']}")
        print(f"    asked on: section_found {b.get('section_found')}, missing {b.get('missing')}, "
              f"lost {b.get('lost')}, numbers {b.get('lost_ins')}")
        c = r.get("check")
        if c and c.get("glued"):
            print(f"    read glued to a neighbour: {c['glued']}")
        for w, where in (r.get("origin") or {}).items():
            print(f"    missing {w!r}: {where}")
    asks = sum(1 for r in out if r["after"])
    print(f"\n{len(out)} clearer-photo requests since {args.since}: before {len(out)} asked, today {asks} would ask.")


if __name__ == "__main__":
    main()

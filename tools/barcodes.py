#!/usr/bin/env python3
"""
Correct a product's barcode, the reviewed way (D-142), and show the record.

The barcode is the catalogue key (D-024). A wrong one serves this pack's result
to whoever scans that code, and hides it from whoever scans the right one. It
is changed only here (or while a never-published product is reviewed): the old
code, the new one, who, when and why are kept in barcode_changes, and the
database refuses any other change (migration 020). No direct SQL.

    export INSIDELABEL_DB=...
    python tools/barcodes.py history 42                    # a product's barcode record
    python tools/barcodes.py history 4901196008343         # every change touching a code
    python tools/barcodes.py fix 42 8901499008343 --by sushil \
        --why "printed under the bars on the back photo: 8 901499 008343" \
        --photo 03f8277a...bae974.jpg                     # dry run: says what would change
    python tools/barcodes.py fix ... --yes                 # the change

--by is an active reviewer account (tools/reviewers.py list). The new code must
pass barcode.check() and belong to no other product.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from insidelabel import barcode as barcode_rules  # noqa: E402
from insidelabel.review.service import ReviewError, ReviewService  # noqa: E402


def _is_code(arg):
    return arg.isdigit() and len(arg) >= 8          # product ids are short; barcodes are 8 to 14 digits


def _product(db, pid):
    with psycopg.connect(db, row_factory=dict_row) as c:
        return c.execute(
            """SELECT p.id, p.name, p.barcode,
                      (SELECT count(*) FROM product_versions v WHERE v.product_id = p.id
                        AND v.status = 'published') AS published,
                      (SELECT count(*) FROM scans s JOIN product_versions v ON v.id = s.product_version_id
                        WHERE v.product_id = p.id) AS scans
                 FROM products p WHERE p.id = %s""", (pid,)).fetchone()


def history(svc, arg, out=print):
    rows = svc.barcode_history(code=arg, product_id=None) if _is_code(arg) else \
        svc.barcode_history(product_id=int(arg))
    if not _is_code(arg):
        p = _product(svc.conninfo, int(arg))
        if p is None:
            out(f"no product #{arg}")
            return rows
        out(f"product #{p['id']} {p['name']}: barcode {p['barcode']} "
            f"({p['published']} published version(s), {p['scans']} scan(s))")
    if not rows:
        out("no recorded barcode changes")
    for r in rows:
        out(f"{r['created_at']:%Y-%m-%d %H:%M} #{r['product_id']} {r['product_name']}: "
            f"{r['old_barcode']} -> {r['new_barcode']} by {r['changed_by']} ({r['via']})")
        out(f"    why: {r['reason']}" + (f"  evidence: {r['evidence']}" if r["evidence"] else ""))
    return rows


def fix(svc, pid, new, by, why, photo=None, yes=False, out=print):
    p = _product(svc.conninfo, pid)
    if p is None:
        raise ReviewError(f"No product #{pid}.")
    code, reason = barcode_rules.check(new)
    shown = code or new
    out(f"product #{p['id']} {p['name']} ({p['published']} published version(s), {p['scans']} scan(s))")
    out(f"barcode {p['barcode']} -> {shown}")
    if not yes:
        if reason:
            raise ReviewError(f"Barcode: {barcode_rules.MESSAGES[reason]}")
        out("dry run: nothing changed (--yes to change it)")
        return None
    row = svc.correct_barcode(pid, new, by, why, evidence=photo)
    out(f"changed (record #{row['id']}): {row['old_barcode']} -> {row['new_barcode']} by {row['changed_by']}")
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("history", help="a product's barcode record, or every change touching a code")
    h.add_argument("product_or_code")
    f = sub.add_parser("fix", help="change a product's barcode (dry run without --yes)")
    f.add_argument("product_id", type=int)
    f.add_argument("new_barcode")
    f.add_argument("--by", required=True, help="your reviewer account")
    f.add_argument("--why", required=True, help="where the right code was read")
    f.add_argument("--photo", help="the photo key the printed digits are on")
    f.add_argument("--yes", action="store_true", help="make the change")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    svc = ReviewService(a.db, engine_version=None)
    try:
        if a.cmd == "history":
            history(svc, a.product_or_code)
        else:
            fix(svc, a.product_id, a.new_barcode, a.by, a.why, a.photo, a.yes)
    except ReviewError as e:
        sys.exit(f"refused: {e}")


if __name__ == "__main__":
    main()

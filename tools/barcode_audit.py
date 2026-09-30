#!/usr/bin/env python3
"""
Every published product's barcode against what its own photos show (D-142).

Found by the barcode measurement of 2026-09-30: product 42 was published under
4901196008343, the camera scanner's read, while the pack prints 8901499008343
(Sushil, by eye). This looks for any other. Read-only: no Gemini, no Cloud Vision (the OCR text is the
one stored on each scan, D-093), nothing written. zxing-cpp reads the photos
as /check-photo does (barcode.read_from_photo), and the
stored OCR text is searched for the digits printed under the bars
(barcode.codes_in_text).

For each product with a published version, the photos are every version's and
every scan's (those not yet deleted, D-080). The product is:
  MISMATCH     zxing reads a code from its photos and it isn't the product's
  unconfirmed  neither zxing nor the OCR text shows the product's code (the
               barcode may just not be in the photos; the OCR's own codes are listed)
  confirmed    zxing or the OCR text shows the product's code
  no photos    none left to read
A product whose code nothing confirms is also listed as SUSPECT when that code came
from the camera scanner and its GS1 prefix (first 3 digits) is not 890 and not the
prefix of another published product of the same brand (Sushil, 2026-09-30: every
other camera read was 890 or a known brand's code; #48's 4992146143214 is not).
Suspect is a reason to photograph the pack's barcode, not a finding.

    INSIDELABEL_MEDIA=... INSIDELABEL_DB=... python tools/barcode_audit.py
    il tools/barcode_audit.py                       # on the server
    il tools/barcode_audit.py --all                 # confirmed products listed too

A mismatch is corrected with tools/barcodes.py fix, after a person has read the
printed digits on the photo; never from this list alone.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel import barcode  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402

PRODUCTS = """
SELECT p.id, p.name, p.barcode, p.brand_id, b.name AS brand,
       EXISTS (SELECT 1 FROM scans s JOIN product_versions v ON v.id = s.product_version_id
                WHERE v.product_id = p.id AND s.request->>'barcode' = p.barcode
                  AND s.request->>'barcode_source' = 'camera') AS camera_read,
       (SELECT array_agg(DISTINCT k) FROM (
          SELECT unnest(ARRAY[v.back_image_key, v.front_image_key]) FROM product_versions v WHERE v.product_id = p.id
          UNION ALL
          SELECT unnest(ARRAY[s.back_image_key, s.front_image_key]) FROM scans s
            JOIN product_versions v ON v.id = s.product_version_id WHERE v.product_id = p.id
        ) AS x(k) WHERE k IS NOT NULL) AS photos,
       (SELECT array_agg(s.ocr->'back'->>'text') FROM scans s
          JOIN product_versions v ON v.id = s.product_version_id
         WHERE v.product_id = p.id AND s.ocr->'back'->>'text' IS NOT NULL) AS ocr_texts,
       (SELECT array_agg(DISTINCT (s.request->>'barcode') || ' (' || COALESCE(s.request->>'barcode_source', '?') || ')')
          FROM scans s JOIN product_versions v ON v.id = s.product_version_id
         WHERE v.product_id = p.id AND s.request->>'barcode' IS NOT NULL) AS sent
  FROM products p
  LEFT JOIN brands b ON b.id = p.brand_id
 WHERE p.barcode IS NOT NULL
   AND EXISTS (SELECT 1 FROM product_versions v WHERE v.product_id = p.id AND v.status = 'published')
 ORDER BY p.id
"""


# The prefix of the catalogue's own packs (Sushil, 2026-09-30); a camera read with
# another one, that no other pack of the brand shares, is worth a second look.
HOME_PREFIX = "890"


def products(db):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(db, row_factory=dict_row) as conn:
        conn.read_only = True
        return conn.execute(PRODUCTS).fetchall()


def audit(rows, media):
    """Each product with what its photos and OCR show, and its class."""
    out = []
    for p in rows:
        read, missing = {}, 0
        for key in sorted(p["photos"] or []):
            got = media.get(key)
            if got is None:
                missing += 1
                continue
            codes, _why = barcode.read_from_photo(got[0])
            if codes:
                read[key] = codes
        zxing = sorted({c for codes in read.values() for c in codes})
        ocr = []
        for text in p["ocr_texts"] or []:
            ocr += [c for c in barcode.codes_in_text(text) if c not in ocr]
        have = len(p["photos"] or []) - missing
        if p["barcode"] in zxing or p["barcode"] in ocr:
            status = "confirmed"
        elif zxing:
            status = "MISMATCH"
        elif have:
            status = "unconfirmed"
        else:
            status = "no photos"
        out.append({**p, "zxing": zxing, "read": read, "ocr": ocr, "status": status,
                    "photos_here": have, "photos_gone": missing})
    for r in out:
        r["suspect"] = suspect(r, out)
    return out


def suspect(r, rows):
    """Why a camera read nothing confirms looks wrong, or None."""
    code = r["barcode"] or ""
    if r["status"] not in ("unconfirmed", "no photos") or not r.get("camera_read") or len(code) != 13:
        return None
    prefix = code[:3]
    if prefix == HOME_PREFIX:
        return None
    if any(o["id"] != r["id"] and r.get("brand_id") is not None and o.get("brand_id") == r["brand_id"]
           and (o["barcode"] or "")[:3] == prefix for o in rows):
        return None
    return (f"a camera read with prefix {prefix}, not {HOME_PREFIX}, and no other published product of "
            f"{r.get('brand') or 'its brand'} has it")


def report(rows, show_all=False, out=print):
    count = {}
    for r in rows:
        count[r["status"]] = count.get(r["status"], 0) + 1
    suspects = [r for r in rows if r.get("suspect")]
    out(f"published products: {len(rows)}  " + "  ".join(
        f"{k}: {count.get(k, 0)}" for k in ("MISMATCH", "unconfirmed", "confirmed", "no photos"))
        + f"  (SUSPECT: {len(suspects)})")
    if suspects:
        out("\nSUSPECT (photograph the pack's barcode):")
        for r in suspects:
            out(f"  #{r['id']} {r['name']}: barcode {r['barcode']}: {r['suspect']}")
    for status in ("MISMATCH", "unconfirmed", "no photos") + (("confirmed",) if show_all else ()):
        chosen = [r for r in rows if r["status"] == status]
        if not chosen:
            continue
        out(f"\n{status}:")
        for r in chosen:
            out(f"  #{r['id']} {r['name']}: barcode {r['barcode']}; scans sent {', '.join(r['sent'] or []) or '-'}")
            for key, codes in sorted(r["read"].items()):
                out(f"      zxing {', '.join(codes)} on {key}")
            if r["ocr"]:
                out(f"      OCR text shows {', '.join(r['ocr'])}")
            out(f"      photos: {r['photos_here']} read, {r['photos_gone']} deleted")
    return count


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    ap.add_argument("--all", action="store_true", help="list confirmed products too")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    if not os.path.isdir(a.media):
        sys.exit(f"no media directory at {a.media}")
    report(audit(products(a.db), LocalMedia(a.media)), show_all=a.all)


if __name__ == "__main__":
    main()

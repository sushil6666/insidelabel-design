"""
pictures.py - the pack picture (D-182): a real photo of a pack's front, shown on every
result for its barcode.

Why it exists: a barcode hit takes no photo, so its result card had nothing to show,
and a real pack reads better than an icon (Sushil, 2026-10-08). Retailer, GS1 and
Open Food Facts images were ruled out (D-088, D-029); the pictures are our own.

Only a person makes one, on /review: a reviewer uploads a photo, or ticks a shopper's
front photo on a review item. The review agent (D-117) never does; it never calls
this module. A shopper's photo qualifies only when its install agreed to the terms
that say a front photo may be shown to others (TERMS_FROM, data/terms.json).

What is stored is a small copy: the long edge at most 480 px, JPEG, rotated by its
EXIF orientation and then saved without any metadata (no camera, no place, no time).
The copy has its own key, so the shopper's own photo still goes at 30 days (D-098).

The picture is never read for findings (D-004): it only shows what the pack looks like.
"""

import datetime as dt
import io

import psycopg
from PIL import Image, ImageOps
from psycopg.rows import dict_row

LONG_EDGE = 480
QUALITY = 80
# The first terms that tell a shopper their front photo may be shown to others.
# Versions are ISO dates (a second one on a day adds "-2", D-184), so a later version
# compares greater.
TERMS_FROM = "2026-10-08"


class PictureError(Exception):
    """A photo that can't become a pack picture (shown to the reviewer)."""


def shrink(data):
    """The small, metadata-free JPEG copy of a photo. PictureError if it can't be read."""
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        im.thumbnail((LONG_EDGE, LONG_EDGE))
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            im = bg
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=QUALITY, optimize=True)   # no exif= : none kept
        return out.getvalue()
    except Exception as e:                       # PIL raises many kinds for a file it can't read
        raise PictureError("This photo can't be read. Use a JPEG or PNG.") from e


def _connect(conninfo):
    return psycopg.connect(conninfo, row_factory=dict_row)


def shopper_front(conninfo, front_key):
    """
    The scan that sent this front photo, when its install agreed to TERMS_FROM or later:
    {scan_id, taken_on}. None when no such scan (older terms, the link already dropped
    after 30 days, D-128, or a photo that isn't a shopper's).
    """
    if not front_key:
        return None
    with _connect(conninfo) as c:
        return c.execute(
            """SELECT s.id AS scan_id, s.created_at::date AS taken_on FROM scans s
                WHERE s.front_image_key = %s AND s.user_id IS NOT NULL
                  AND EXISTS (SELECT 1 FROM agreements a
                               WHERE a.user_id = s.user_id AND a.terms_version >= %s)
                ORDER BY s.created_at LIMIT 1""", (front_key, TERMS_FROM)).fetchone()


def product_of(conninfo, *, barcode=None, version_id=None):
    """The product id for a barcode or a version, or None."""
    with _connect(conninfo) as c:
        if version_id:
            row = c.execute("SELECT product_id AS id FROM product_versions WHERE id = %s", (version_id,)).fetchone()
        else:
            row = c.execute("SELECT id FROM products WHERE barcode = %s", (barcode,)).fetchone()
    return row and row["id"]


def add(conninfo, media, *, product_id, data, source, approved_by, scan_id=None, taken_on=None):
    """Store the small copy and show it for this product. Returns the new row."""
    key = media.put(shrink(data), "image/jpeg")
    with _connect(conninfo) as c:
        return c.execute(
            """INSERT INTO pack_pictures (product_id, image_key, source, scan_id, taken_on, approved_by)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (product_id, key, source, scan_id, taken_on or dt.date.today(), approved_by)).fetchone()


def remove(conninfo, picture_id, by):
    """Stop showing a picture (kept as a row: who approved and who removed it). True if it was shown."""
    with _connect(conninfo) as c:
        return c.execute("""UPDATE pack_pictures SET removed_at = now(), removed_by = %s
                             WHERE id = %s AND removed_at IS NULL""", (by, picture_id)).rowcount == 1


def current(conninfo, product_id):
    """The picture shown for a product (the newest not removed), or None."""
    with _connect(conninfo) as c:
        return c.execute("""SELECT * FROM pack_pictures WHERE product_id = %s AND removed_at IS NULL
                             ORDER BY approved_at DESC, id DESC LIMIT 1""", (product_id,)).fetchone()


def shown(conninfo, key):
    """True when this key is a picture being shown (the public route serves nothing else)."""
    with _connect(conninfo) as c:
        return c.execute("SELECT 1 FROM pack_pictures WHERE image_key = %s AND removed_at IS NULL",
                         (key,)).fetchone() is not None


def recent(conninfo, limit=50):
    """The newest pictures shown, with their product, for /review/pictures."""
    with _connect(conninfo) as c:
        return c.execute(
            """SELECT pp.*, p.name AS product_name, p.barcode, b.name AS brand FROM pack_pictures pp
                 JOIN products p ON p.id = pp.product_id LEFT JOIN brands b ON b.id = p.brand_id
                WHERE pp.removed_at IS NULL ORDER BY pp.approved_at DESC LIMIT %s""", (limit,)).fetchall()

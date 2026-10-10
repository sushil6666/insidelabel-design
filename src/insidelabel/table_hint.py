"""
table_hint.py - D-191: a free check that a "list" photo is the nutrition table.

Why (Sushil, 2026-10-10): of 13 `no_ingredient_list_found` scans in a week (besides the
Ayurvedic pack), 10 had a nutrition table read but no list: people photographed the table
and paid about 9 s per retake. A local Tesseract read of the first list photo, before the
paid read, can ask once: "This looks like the nutrition table. Is the ingredient list in
it?" ("Retake", "Use this photo"). Words in lenses/screen.py (D-091), word lists in
data/table_hint.json.

Off by default (INSIDELABEL_TABLE_HINT=on to turn it on). It goes on only when
tools/table_hint_measure.py's numbers (false alarms, catches, time) are accepted. At most
one check per scan: the app asks for it on the first list photo only. A read that takes
longer than READ_CAP_S gives no hint, so it never holds a photo up for long. It never
refuses a photo and nothing is stored; the AI-reads-rules-judge line (D-004) is not
touched: the hint is a question, not a finding.
"""

import io
import json
import os
import re
import time

from insidelabel.core.engine import DATA_DIR

try:
    import pytesseract
    from PIL import Image, ImageOps
    AVAILABLE = True
except ImportError:                                              # pragma: no cover
    AVAILABLE = False

WORDS = json.load(open(os.path.join(DATA_DIR, "table_hint.json"), encoding="utf-8"))
READ_CAP_S = 3.0
LONG_EDGE = 1200


def enabled():
    return os.environ.get("INSIDELABEL_TABLE_HINT", "").strip().lower() == "on"


def looks_like_table(text):
    """The rule on a text: {"fires", "table_words", "list_word"}. No read, no time."""
    low = " ".join((text or "").lower().split())
    found = sorted({w for w in WORDS["table_words"] if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low)})
    listed = any(w in low for w in WORDS["list_words"])
    return {"fires": len(found) >= WORDS["min_table_words"] and not listed,
            "table_words": found, "list_word": listed}


def read(image_bytes):
    """One Tesseract pass on a grey copy, long edge LONG_EDGE px; None past READ_CAP_S."""
    if not AVAILABLE or not image_bytes:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("L")
        im.thumbnail((LONG_EDGE, LONG_EDGE))
        return pytesseract.image_to_string(ImageOps.autocontrast(im), config="--psm 3", timeout=READ_CAP_S)
    except Exception:                                            # noqa: BLE001 - a timeout or a bad file: no hint
        return None


def check(image_bytes, reader=None):
    """The check on a photo: looks_like_table() on its read (read() unless given), with the read's ms."""
    t0 = time.monotonic()
    text = (reader or read)(image_bytes)
    out = looks_like_table(text) if text is not None else {"fires": False, "table_words": [], "list_word": False}
    out.update(read=text is not None, ms=int((time.monotonic() - t0) * 1000))
    return out

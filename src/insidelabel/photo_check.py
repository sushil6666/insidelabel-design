"""
photo_check.py - is this upload a photo we could read at all? (D-103)

Runs before the model is called, so a file that can't be a readable label
never costs a Gemini read. Checks only what needs no judgement: it decodes as
an image, it is big enough to hold legible label text, and it isn't blank
(a pocket, a lens cap, a black frame). Whether it shows a food pack is the
model's reading, decided by rules afterwards (reliability/gates.py).

HEIC/HEIF can't be decoded here without an extra library; those pass through
to the model, which reads them. The app converts photos to JPEG anyway.
"""

import io

from PIL import Image, ImageStat

# Label text needs pixels. Set below the smallest photo the model has read
# correctly: the gold Limca 1 L back is 528x572 and Limca 2.25 L 480x640
# (INS F1 1.0 on both). The app itself sends 1600 px on the long edge.
MIN_LONG_EDGE = 480
MIN_SHORT_EDGE = 240
# Standard deviation of grey levels, 0-255. Measured on the 12 gold photos:
# 33.5-67.6. A blank, black or lens-cap frame is ~0-5.
MIN_CONTRAST = 8
_UNDECODED = {"image/heic", "image/heif"}

MESSAGES = {
    "not_an_image": "The {role} file isn't a photo we can read. Take a photo of the pack, or upload a JPEG or PNG.",
    "photo_too_small": "The {role} photo is too small to read the label. Take it again, closer to the pack.",
    "photo_blank": "The {role} photo is almost blank or very dark. Take it again in good light.",
}


def check(data, mime, role, min_size=True):
    """
    None when the photo can go to the model, else (code, message). A close-up
    of a barcode needs no label-sized pixels (min_size=False, D-104).
    """
    if mime in _UNDECODED:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()                          # a truncated or fake file fails here
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        if min_size and (max(w, h) < MIN_LONG_EDGE or min(w, h) < MIN_SHORT_EDGE):
            return "photo_too_small", MESSAGES["photo_too_small"].format(role=role)
        im.draft("L", (400, 400))                # JPEG: decode small, fast
        grey = im.convert("L")
        grey.thumbnail((400, 400))
        if ImageStat.Stat(grey).stddev[0] < MIN_CONTRAST:
            return "photo_blank", MESSAGES["photo_blank"].format(role=role)
    except (OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        return "not_an_image", MESSAGES["not_an_image"].format(role=role)
    return None

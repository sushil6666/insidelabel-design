"""
Join the parts of a long ingredient list into one back photo (D-119).

On a big pack the list doesn't fit one photo, or fits only from so far away
that the letters are too small to read. The app then sends it in up to three
parts, in the order taken. They are joined here, one above the other, into a
single image, and from then on the scan is ordinary: one back photo for
Gemini (whose reading prompt stays frozen, D-081), for Cloud Vision, for
storage, review, replay (D-092) and the 30-day cleanup (D-098).

A strip of plain grey separates the parts, so a reader sees photos of one
list rather than one printed label. Parts are scaled to one width, so the
text keeps its size from part to part.
"""

import io

from PIL import Image, ImageOps

MAX_PARTS = 3
GAP = 16                 # px of grey between parts
GAP_COLOUR = (200, 200, 200)
MAX_WIDTH = 1600         # the app's own longest edge (prepareImage)
MAX_SIDE = 4800          # the joined image's longest side: three app-sized parts


class JoinError(ValueError):
    """A part that can't be decoded here (e.g. HEIC from an API client)."""


def join(parts):
    """parts: [(bytes, mime)] in the order taken, at least two. Returns (jpeg bytes, 'image/jpeg')."""
    if not 2 <= len(parts) <= MAX_PARTS:
        raise JoinError(f"a list is sent in 2 to {MAX_PARTS} parts")
    imgs = []
    for n, (data, _mime) in enumerate(parts, 1):
        try:
            im = Image.open(io.BytesIO(data))
            im = ImageOps.exif_transpose(im).convert("RGB")
        except Exception as e:                                   # noqa: BLE001 - any undecodable file
            raise JoinError(f"part {n} can't be read here; send the parts as JPEG, PNG or WebP") from e
        imgs.append(im)

    width = min(max(i.width for i in imgs), MAX_WIDTH)
    scaled = [i if i.width == width else i.resize((width, max(1, round(i.height * width / i.width))),
                                                  Image.LANCZOS) for i in imgs]
    height = sum(i.height for i in scaled) + GAP * (len(scaled) - 1)
    out = Image.new("RGB", (width, height), GAP_COLOUR)
    y = 0
    for i in scaled:
        out.paste(i, (0, y))
        y += i.height + GAP
    if max(out.size) > MAX_SIDE:
        f = MAX_SIDE / max(out.size)
        out = out.resize((max(1, round(out.width * f)), max(1, round(out.height * f))), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"

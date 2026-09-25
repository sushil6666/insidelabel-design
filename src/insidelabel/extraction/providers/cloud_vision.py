"""
Google Cloud Vision OCR, as the independent reader for ocr_check.py (D-093).

Why it replaces Tesseract as the first choice: on the first traced scan (D-092)
the Tesseract cross-check took 28 s of a 28.6 s scan, because it reads the back
photo up to nine times (six voting passes, one text read, two identity reads).
Cloud Vision reads each photo once; the text is cached by content hash so every
check on the same photo reuses it.

Why it is still independent of Gemini (D-034): it is a dedicated OCR system,
not the generative model that produced the ingredient list, so it has no idea
which ingredient is "minor" and no way to leave one out on purpose. Same vendor,
different system; noted in D-093.

Only ever used to *detect*: ocr_check.py keeps the same asymmetry and the same
guards whichever reader supplied the text.

Configure with GOOGLE_VISION_KEY (an API key restricted to the Vision API).
Without it, or when a call fails, ocr_check.py falls back to Tesseract.
"""

import base64
import hashlib
import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections import OrderedDict

log = logging.getLogger("insidelabel.ocr")

ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
TIMEOUT_S = 12
# The API takes up to 20 MB per request; base64 adds a third. Big phone photos
# are shrunk first: label text is legible well below this size.
MAX_SEND_BYTES = 4_000_000
MAX_LONG_EDGE = 3200

_CACHE = OrderedDict()
_CACHE_SIZE = 32
LAST = {}          # the last call's outcome, for diagnostics: {ms, status, cached}

# Circuit breaker. One scan can ask for up to four reads; while Cloud Vision is
# failing, each would cost a round trip before the Tesseract fallback. So after
# a failure it is skipped for a while: a configuration error (billing off, key
# restricted, API disabled) won't fix itself in seconds; a timeout might.
DOWN_CONFIG_S = 600
DOWN_TRANSIENT_S = 60
_down_until = 0.0


def _trip(seconds, status):
    global _down_until
    _down_until = time.monotonic() + seconds
    LAST["status"] = status


def configured():
    return bool(os.environ.get("GOOGLE_VISION_KEY"))


def _shrink(image_bytes):
    if len(image_bytes) <= MAX_SEND_BYTES:
        return image_bytes
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(image_bytes))
        im.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:                                            # noqa: BLE001
        return image_bytes


def read_text(image_bytes):
    """Full text of the image, or None when the call fails (the caller falls back)."""
    key = os.environ.get("GOOGLE_VISION_KEY")
    if not key or not image_bytes:
        return None
    if time.monotonic() < _down_until:
        LAST.update(ms=0, status=LAST.get("status", "down"), cached=False, skipped=True)
        return None
    digest = hashlib.sha256(image_bytes).hexdigest()
    if digest in _CACHE:
        _CACHE.move_to_end(digest)
        LAST.update(ms=0, status="ok", cached=True)
        return _CACHE[digest]

    body = json.dumps({"requests": [{
        "image": {"content": base64.b64encode(_shrink(image_bytes)).decode()},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        # English first; Hindi because many Indian packs print a Devanagari block.
        "imageContext": {"languageHints": ["en", "hi"]},
    }]}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-Goog-Api-Key": key})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # The body names the problem (key restricted, API not enabled, quota…),
        # never the key itself.
        detail = e.read()[:300].decode(errors="replace")
        LAST.update(ms=int((time.monotonic() - t0) * 1000), cached=False, skipped=False)
        transient = e.code == 429 or e.code >= 500
        _trip(DOWN_TRANSIENT_S if transient else DOWN_CONFIG_S, f"http_{e.code}")
        log.warning("Cloud Vision HTTP %s: %s", e.code, detail)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        LAST.update(ms=int((time.monotonic() - t0) * 1000), cached=False, skipped=False)
        _trip(DOWN_TRANSIENT_S, type(e).__name__)
        log.warning("Cloud Vision call failed: %s", type(e).__name__)
        return None

    LAST.update(ms=int((time.monotonic() - t0) * 1000), cached=False, skipped=False)
    resp = (data.get("responses") or [{}])[0]
    if resp.get("error"):
        _trip(DOWN_TRANSIENT_S, "api_error")
        log.warning("Cloud Vision error: %s", resp["error"].get("message"))
        return None
    LAST["status"] = "ok"
    text = (resp.get("fullTextAnnotation") or {}).get("text") or ""
    _CACHE[digest] = text
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return text

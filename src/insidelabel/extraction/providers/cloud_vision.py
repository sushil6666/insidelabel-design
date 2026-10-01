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

Replays (D-092): every scan row keeps the text this module returned (migration
007). repro.py puts it back with `replaying()`, so a replay reads exactly what
the scan read, never calls Google, and works when the photo itself is gone.
"""

import base64
import contextlib
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
# scan-speed (2026-10-01): from 18:02 UTC every call answered HTTP 200 with a
# per-image {"code": 8, "message": "Resource has been exhausted (e.g. check
# quota)."}. That is an outage, not a blip: like an HTTP 429 it trips the breaker
# for 10 minutes (it was 60 s, so one long scan called Google twice) and raises
# the alarm once per trip, so it reaches the problem reports, not just slow scans.
DOWN_OUTAGE_S = 600
OUTAGE_CODES = {8}                  # google.rpc RESOURCE_EXHAUSTED
_down_until = 0.0
# A configuration failure (billing off, key restricted…) silently costs every
# scan the slow Tesseract fallback. The API takes this alarm once per trip and
# files it as a 'server' problem report (D-092) so it doesn't go unnoticed.
_alarm = None


def _trip(seconds, status, config=False):
    global _down_until, _alarm
    _down_until = time.monotonic() + seconds
    LAST["status"] = status
    if config:
        _alarm = status


def alarm_text(status):
    """The problem report's words for a trip: what refused, and what scans do now."""
    what = (f"code {status.split('_', 1)[1]}" if status.startswith("code_")
            else f"HTTP {status.split('_', 1)[1]}" if status.startswith("http_") else status)
    return (f"Cloud Vision refused ({what}): scans use the fallback reader (Tesseract) for the next "
            f"{DOWN_OUTAGE_S // 60} minutes, then try Google again. See OPERATIONS.md section 6.")


def take_alarm():
    """The configuration failure since the last call, once, or None."""
    global _alarm
    alarm, _alarm = _alarm, None
    return alarm


# Replay mode: {sha256 of the photo: stored text}, or None in normal running.
# While set, no call leaves this machine: a photo with stored text gets that
# text, any other photo gets None (the caller falls back to Tesseract). A module
# global, not a context variable, because the reads run on worker threads. Only
# repro.py (a CLI and the tests) sets it; the server never does.
_REPLAY = None


@contextlib.contextmanager
def replaying(texts):
    """Serve reads from recorded text, by photo hash, instead of Google."""
    global _REPLAY
    old, _REPLAY = _REPLAY, dict(texts or {})
    try:
        yield
    finally:
        _REPLAY = old


def replay_active():
    """In replay mode with recorded text to serve (so the Cloud Vision path applies)."""
    return bool(_REPLAY)


def configured():
    return bool(os.environ.get("GOOGLE_VISION_KEY"))


def digest(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()


def cached(image_bytes):
    """The text already read for this photo (or replayed for it), else None. Never calls Google."""
    if not image_bytes:
        return None
    d = digest(image_bytes)
    if _REPLAY is not None:
        return _REPLAY.get(d)
    return _CACHE.get(d)


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
    if _REPLAY is not None:
        text = _REPLAY.get(digest(image_bytes)) if image_bytes else None
        LAST.update(ms=0, status="replayed" if text is not None else "not_recorded", cached=True)
        return text
    key = os.environ.get("GOOGLE_VISION_KEY")
    if not key or not image_bytes:
        return None
    if time.monotonic() < _down_until:
        LAST.update(ms=0, status=LAST.get("status", "down"), cached=False, skipped=True)
        return None
    d = digest(image_bytes)
    if d in _CACHE:
        _CACHE.move_to_end(d)
        LAST.update(ms=0, status="ok", cached=True)
        return _CACHE[d]

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
        if e.code == 429:
            _trip(DOWN_OUTAGE_S, "http_429", config=True)
        else:
            transient = e.code >= 500
            _trip(DOWN_TRANSIENT_S if transient else DOWN_CONFIG_S, f"http_{e.code}", config=not transient)
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
        code = resp["error"].get("code")
        if code in OUTAGE_CODES:
            _trip(DOWN_OUTAGE_S, f"code_{code}", config=True)
        else:
            _trip(DOWN_TRANSIENT_S, "api_error")
        log.warning("Cloud Vision error (code %s): %s", code, resp["error"].get("message"))
        return None
    LAST["status"] = "ok"
    text = (resp.get("fullTextAnnotation") or {}).get("text") or ""
    _CACHE[d] = text
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return text

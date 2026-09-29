"""
repro.py - replay a stored scan exactly, to reproduce a reported problem (D-092).

Everything after the vision model is deterministic, and each scan row keeps the
model's raw answer, the request options, the build and the data version
(migration 006), and the independent reader's text (007). So a scan is replayed
by sending the same photos, options and model answer through /scan again, with
the stored OCR text standing in for Cloud Vision and storage switched off, so a
replay never calls Google and never writes to the database or the media store.

What the user saw comes from the phone's trail (`shown` on the /scan event):
state, headline, band and each profile's status, without names. Comparing it
with the replay says whether today's code still does the same thing.

Used by tools/repro.py (the CLI) and tests/test_problem_regressions.py.
"""

import base64
import contextlib
import json

from fastapi.testclient import TestClient

from insidelabel import ratelimit, trace
from insidelabel.api import main
from insidelabel.extraction.providers import cloud_vision

# The 1x1 PNG the test suite uses: saved regressions carry no photos (photos can
# hold the shop's location in EXIF, and they stay out of git).
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def summary(screen):
    """Same fields as screenSummary() in web/lib.js."""
    if not screen:
        return None
    return {"state": screen.get("state"), "headline": (screen.get("headline") or {}).get("text"),
            "band": (screen.get("band") or {}).get("code"),
            "people": [f"{p['ref']}:{p['status']}" for p in screen.get("people") or []]}


@contextlib.contextmanager
def no_storage():
    """
    Run the API with nothing persisted: a replay must not create scans or photos.
    Rate limits (D-095) are off too: replaying a long trail isn't a flood.
    Replay is allowed here whatever the environment says (D-101). The invite gate
    (D-102/D-105) is off too: the scan was let in when it ran, and with no store the
    gate answers 503 storage_unavailable on a server with INSIDELABEL_INVITE_ONLY=on.
    """
    old = main.STORE, main.MEDIA, ratelimit.LIMITER.rules, main.REPLAY_ALLOWED, main.INVITE_ONLY
    main.STORE, main.MEDIA, ratelimit.LIMITER.rules, main.REPLAY_ALLOWED, main.INVITE_ONLY = None, None, {}, True, False
    try:
        yield
    finally:
        main.STORE, main.MEDIA, ratelimit.LIMITER.rules, main.REPLAY_ALLOWED, main.INVITE_ONLY = old


def form_for(request, model_raw):
    """The /scan form fields that recreate a stored request."""
    data = {"replay": model_raw,
            "pairing_confirmed": "true" if request.get("pairing_confirmed") else "false",
            "compare_regulators": "true" if request.get("compare_regulators") else "false"}
    if request.get("profiles"):
        data["profiles"] = json.dumps(request["profiles"])
    if request.get("avoid") is not None:
        data["avoid"] = ",".join(request["avoid"])
    if request.get("barcode"):
        data["barcode"] = request["barcode"]
    if request.get("screen_pack"):
        data["screen_pack"] = json.dumps(request["screen_pack"])          # D-130
    return data


def ocr_texts(ocr, files):
    """{photo hash: text} for cloud_vision.replaying(): the stored read, on the photo sent now."""
    out = {}
    for role, rec in (ocr or {}).items():
        if role in files and (rec or {}).get("reader") == "cloud_vision" and rec.get("text") is not None:
            out[cloud_vision.digest(files[role][1])] = rec["text"]
    return out


def post_scan(data, files, ocr=None):
    """Replay /scan. `ocr` is the scan row's stored OCR ({} or None: Tesseract, never Google)."""
    with no_storage(), cloud_vision.replaying(ocr_texts(ocr, files or {})):
        r = TestClient(main.app).post("/scan", data=data, files=files or None)
    body = r.json()
    return {"status": r.status_code, "screen": body.get("screen"), "body": body}


def replay_scan(scan, media=None, hit=None):
    """
    Re-run one stored scan on today's code. Returns {status, screen, notes, ...};
    status None means it can't be replayed (the model never answered).
    """
    notes, req = [], scan.get("request") or {}
    if scan.get("build") and scan["build"] != trace.BUILD:
        notes.append(f"code changed since: scan ran {scan['build']}, now {trace.BUILD}")
    if scan.get("data_version") and scan["data_version"] != trace.DATA_VERSION:
        notes.append(f"data tables changed since: {scan['data_version']} → {trace.DATA_VERSION}")

    if scan.get("cache_hit"):
        if hit is None:
            return {"status": None, "notes": notes + ["catalogue version no longer found"]}
        result = main._catalogue_result(hit, req.get("avoid") or [], None,
                                        bool(req.get("compare_regulators")), req.get("profiles") or [])
        return {"status": 200, "screen": result["screen"], "body": result, "notes": notes}

    if not scan.get("model_raw"):
        return {"status": None, "notes": notes + [
            f"nothing to replay: outcome {scan.get('outcome')}, the model never answered"]}

    ocr = scan.get("ocr") or {}
    files = {}
    for role, key in (("back", scan.get("back_image_key")), ("front", scan.get("front_image_key"))):
        got = media.get(key) if (media and key) else None
        if got:
            files[role] = (f"{role}.{key.rsplit('.', 1)[1]}", got[0], got[1])
        elif role in (req.get("images") or ["back"]):
            files[role] = (f"{role}.png", PNG, "image/png")
            if (ocr.get(role) or {}).get("text") is not None:
                notes.append(f"{role} photo not available: replayed with the stored OCR text")
            elif role == "back":
                notes.append(f"{role} photo not available: replayed without it, so the OCR cross-check differs")
    if "back" in files and not ocr:
        notes.append("OCR text not stored (scan predates migration 007): cross-check re-read with "
                     "Tesseract, not Google, so it may differ")
    out = post_scan(form_for(req, scan["model_raw"]), files, ocr)
    return {**out, "notes": notes}


def compare(shown, now):
    """Differences between what the user saw and the replay, as readable lines."""
    if shown is None:
        return ["the phone's trail has no record of what was shown"]
    if now is None:
        return ["the replay showed no result screen"]
    return [f"{k}: then {shown.get(k)!r}, now {now.get(k)!r}"
            for k in ("state", "headline", "band", "people") if shown.get(k) != now.get(k)]

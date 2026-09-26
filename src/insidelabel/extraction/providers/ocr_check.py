"""
Inside Label - independent OCR cross-check.

WHY THIS EXISTS
    Every self-check tried so far failed for the same structural reason: a
    model verifying its own output cannot catch its own omission.

      - "confidence" was 1.0 on runs that dropped a printed preservative.
      - ingredients_raw, meant to be a source of truth for the split array,
        turned out to be missing the same item.
      - ingredient_count reconciled perfectly at 5 = 5, because the model
        counts what it transcribed, not what is on the pack.

    An omission is invisible from the inside. It is only visible against an
    independent reader.

    Tesseract is that reader. It is a classical OCR engine with no language
    model, so it has no notion of an ingredient being semantically minor and
    no mechanism for leaving one out. On the label where Gemini dropped
    PRESERVATIVE (211) it returned all five additive numbers.

WHAT THIS IS AND IS NOT
    It is an OMISSION DETECTOR, not a replacement transcriber. Tesseract is
    worse than Gemini at almost everything else here -- it garbles the curved
    legal footer, it will do far worse on foil and glare -- so it is never
    allowed to overwrite the ingredient text. It is allowed to do exactly one
    thing: assert that a specific INS number is present on the label.

    That asymmetry is deliberate. A number Tesseract found and Gemini missed
    is strong evidence, because two independent readers disagreeing in the
    direction of MORE detail is not a shared hallucination. A number Gemini
    found and Tesseract missed means nothing, because Tesseract misses things
    constantly.

    Numbers are only counted when they sit inside an additive class bracket,
    using engine.prefix_bare_ins -- the same rule the engine itself applies.
    So "200 ml" in a garbled footer is not mistaken for sorbic acid.

WHICH READER (D-093)
    Google Cloud Vision first, when GOOGLE_VISION_KEY is set: one call per
    photo, cached, shared by the INS check and the identity checks. Tesseract
    when it isn't set or a call fails -- the same guards apply to both, and the
    result says which reader ran (`reader`). INSIDELABEL_OCR=tesseract forces
    the old path, e.g. to compare the two.
"""

import io
import os
import re

try:
    import pytesseract
    from PIL import Image
    AVAILABLE = True
except ImportError:                                              # pragma: no cover
    AVAILABLE = False

from insidelabel.core import engine
from insidelabel.core.tokenize import INS_RE
from insidelabel.extraction.providers import cloud_vision

_INS = INS_RE  # same pattern the engine uses, so the cross-check cannot disagree with it

# Preprocessing matters enormously here. Measured on a real phone photo of a
# curved 2.25L bottle under indoor light, Tesseract returned ZERO characters
# from the raw JPEG. Grayscale + upscale + autocontrast + sharpen, read with
# --psm 6 (uniform block), recovered readable text.
#
# It still only recovered 1 of the 5 additive numbers on that label. The
# ingredient line curving around the bottle shoulder was unrecoverable. So on
# real photographs this is a WEAK detector: it will sometimes catch an
# omission and will often miss one. Treat a clean pass as "no evidence of an
# omission", never as "no omission".
# Tesseract wants roughly 300 DPI on the TEXT, not a huge image. A phone photo
# is already 3-10 MP, so upscaling it was catastrophic: a 3187x3023 label photo
# became 86.7 MP at x3, and twelve passes over that never finished - the first
# real full-resolution pack hung here until interrupted.
#
# So: normalise to a fixed working size FIRST, then vary. Label text in a
# frame-filling photo is comfortably legible at ~2200px on the long edge, and
# small renders get upscaled to reach it rather than multiplied blindly.
# Two scales, measured rather than guessed. Recall/time across three real
# labels (render, phone photo, 9.6 MP phone photo):
#   2200 only,      3 passes:  5/5, 0/5, 1/5   -  2s /  5s /  9s
#   2200+3200,      6 passes:  5/5, 1/5, 1/5   -  5s / 12s / 22s   <- chosen
#   2200+3200 +psm4, 12 passes: 5/5, 0/5, 1/5  - 12s / 21s / 44s
# psm 4 doubles the cost, adds nothing, and is unstable (it LOST the photo hit).
TARGET_LONG_EDGES = (2200, 3200)
MAX_WORKING_PIXELS = 6_000_000

# Per-call ceiling. Without one a single pathological page blocks the scan with
# no error and no output.
OCR_TIMEOUT_S = 25

# Several passes, then a vote. Individual passes invent numbers -- one pass
# read 471 as 447 -- but a genuine number appears in nearly every pass while a
# misread appears in one or two. Requiring majority agreement kept 211 (12/12
# passes) and rejected 447 (2/12) with no loss of recall.
_MIN_PASS_FRACTION = 0.5


def _cloud():
    """Use Cloud Vision for this call? (auto = when a key is configured)."""
    if cloud_vision._REPLAY is not None:
        # A replay (D-092) uses the reader the scan used: recorded Cloud Vision
        # text when there is some, otherwise Tesseract. Never a new Google call.
        return cloud_vision.replay_active()
    return os.environ.get("INSIDELABEL_OCR", "auto") != "tesseract" and cloud_vision.configured()


def cloud_first():
    """Will the next read go to Cloud Vision? The API uses this to start it early."""
    return _cloud()


def _ins_numbers(text):
    """INS numbers in class-bracket context, by the engine's own rule."""
    # OCR line breaks are layout, not content. On the Ziggy pack the class word
    # and its bracket sit on different lines ("Acidity Regulators\n(330, 270)"),
    # and five printed numbers were lost to the newline alone (D-093).
    text = " ".join((text or "").split())
    return {m.group(1).lower() for m in _INS.finditer(engine.prefix_bare_ins(text))}


def _normalise(im, target):
    """Grayscale, then scale the long edge to `target` (up or down)."""
    from PIL import ImageOps
    g = ImageOps.grayscale(im)
    long_edge = max(g.width, g.height)
    factor = target / long_edge if long_edge else 1.0
    w, h = max(1, int(g.width * factor)), max(1, int(g.height * factor))
    if w * h > MAX_WORKING_PIXELS:
        shrink = (MAX_WORKING_PIXELS / (w * h)) ** 0.5
        w, h = max(1, int(w * shrink)), max(1, int(h * shrink))
    return g.resize((w, h), Image.LANCZOS)


def _prepared(im):
    """
    Yield preprocessed variants, best-first. Three, not nine.

    The previous nine variants x two page-segmentation modes gave no recall
    benefit on the labels measured - every INS number found was found by the
    first variant - while multiplying runtime by twelve.
    """
    from PIL import ImageEnhance, ImageOps
    for target in TARGET_LONG_EDGES:
        ac = ImageOps.autocontrast(_normalise(im, target))
        yield ImageEnhance.Sharpness(ac).enhance(2.0)
        yield ac
        yield ImageOps.invert(ac)


def read_text(image_bytes):
    """Best-effort single read. Cloud Vision when configured (cached), else Tesseract."""
    if _cloud():
        text = cloud_vision.read_text(image_bytes)
        if text is not None:
            return text
    if not AVAILABLE:
        return None
    try:
        im = Image.open(io.BytesIO(image_bytes))
        if im.mode not in ("L", "RGB"):
            im = im.convert("RGB")
        return pytesseract.image_to_string(next(_prepared(im)), config="--psm 6",
                                           timeout=OCR_TIMEOUT_S)
    except Exception:                                            # noqa: BLE001
        return None


def vote_ins(image_bytes):
    """
    Read the image several ways and keep only INS numbers that most passes
    agree on. Returns (accepted, tally, passes) or (None, {}, 0).
    """
    if not AVAILABLE:
        return None, {}, 0
    try:
        im = Image.open(io.BytesIO(image_bytes))
        if im.mode not in ("L", "RGB"):
            im = im.convert("RGB")
    except Exception:                                            # noqa: BLE001
        return None, {}, 0

    tally, passes = {}, 0
    for variant in _prepared(im):
        for psm in ("--psm 6",):
            try:
                text = pytesseract.image_to_string(variant, config=psm,
                                                   timeout=OCR_TIMEOUT_S)
            except Exception:                                    # noqa: BLE001
                # RuntimeError on timeout, or a missing binary. Either way this
                # pass contributes nothing; the vote threshold adapts.
                continue
            passes += 1
            for ins in _ins_numbers(text):
                tally[ins] = tally.get(ins, 0) + 1
    if not passes:
        return None, {}, 0
    threshold = max(2, int(passes * _MIN_PASS_FRACTION))
    voted = {i for i, c in tally.items() if c >= threshold}

    # Only numbers the engine actually knows may be recovered.
    #
    # Measured on a 9.6 MP phone photo: Tesseract read INS 503 as "303" in
    # every configuration tried. Recovery would have injected a fabricated
    # additive into the ingredient list - a fact with no source on a real pack,
    # which is the worst output this system can produce.
    #
    # Restricting to known rows costs nothing real: an INS number absent from
    # additives.json contributes nothing to the verdict anyway, so recovering
    # it gains no accuracy while risking invention. Unknown numbers are still
    # reported for diagnosis, just never injected.
    known = {i for i in voted if i in engine._ADDITIVE_BY_INS}
    return known, {"voted": sorted(voted), "tally": tally,
                   "rejected_unknown": sorted(voted - known)}, passes


def cross_check(image_bytes, ingredients):
    """
    Compare an independent OCR read against the model's ingredient list.

    Returns a dict:
        available        was the check actually run
        ocr_ins          INS numbers the independent reader found
        model_ins        INS numbers in the model's list
        missing          found by OCR, absent from the model  <- the signal
        extra            in the model, not found by OCR       <- expected, ignored
    """
    model_ins = _ins_numbers(", ".join(ingredients or []))
    fallback_reason = None
    if _cloud():
        text = cloud_vision.read_text(image_bytes)
        if text is not None:
            # One read, no vote: Cloud Vision returns the same text for the same
            # image, so repeated passes would add cost, not evidence. The guard
            # that matters stays: only numbers the engine knows can be recovered.
            found = _ins_numbers(text)
            ocr_ins = {i for i in found if i in engine._ADDITIVE_BY_INS}
            return {
                "available": True, "reader": "cloud_vision",
                "ocr_ins": sorted(ocr_ins), "model_ins": sorted(model_ins),
                "missing": sorted(ocr_ins - model_ins), "extra": sorted(model_ins - ocr_ins),
                "vote_detail": {"voted": sorted(found), "rejected_unknown": sorted(found - ocr_ins)},
                "passes": 1, "ms": cloud_vision.LAST.get("ms"), "ocr_text": text,
            }
        fallback_reason = f"cloud_vision {cloud_vision.LAST.get('status', 'failed')}"

    if not AVAILABLE:
        return {"available": False, "reason": "pytesseract not installed", "fallback_from": fallback_reason}

    ocr_ins, vote_detail, passes = vote_ins(image_bytes)
    if ocr_ins is None:
        return {"available": False, "reason": "OCR failed on this image", "fallback_from": fallback_reason}
    text = read_text(image_bytes) or ""
    return {
        "available": True, "reader": "tesseract", "fallback_from": fallback_reason,
        "ocr_ins": sorted(ocr_ins),
        "model_ins": sorted(model_ins),
        "missing": sorted(ocr_ins - model_ins),
        "extra": sorted(model_ins - ocr_ins),
        "vote_detail": vote_detail,
        "passes": passes,
        "ocr_text": text,
    }


def recover_entries(image_bytes, ingredients):
    """
    Build replacement entries for additives the model dropped.

    Only fires on `missing`. The recovered entry is labelled with its
    provenance so nothing downstream mistakes it for something the model read,
    and so a human reviewing a gold file can see exactly where it came from.
    """
    result = cross_check(image_bytes, ingredients)
    if not result.get("available") or not result.get("missing"):
        return list(ingredients or []), result, []

    text = result["ocr_text"]
    recovered = []
    for ins in result["missing"]:
        # Pull the surrounding printed fragment so the entry keeps label wording
        # rather than being synthesised from the number alone.
        m = re.search(
            r"([A-Za-z][A-Za-z \-]{2,30}\([^)]*\b" + re.escape(ins) + r"\b[^)]*\))",
            engine.prefix_bare_ins(text).replace("INS ", ""),
        )
        recovered.append(m.group(1).strip() if m else f"({ins})")

    return list(ingredients or []) + recovered, result, recovered


# ---------------------------------------------------------------------------
# Identity corroboration
# ---------------------------------------------------------------------------
# The product_match anchor check in gemini.py compares front_identity against
# back_identity -- but BOTH are model output, so it verifies that the model
# agrees with itself, not that either value is on the pack.
#
# Observed on consecutive runs of the same photographed bottle: back_identity
# .brand came back as None, then as "Limca". The second run manufactured an
# anchor, flipped product_match from indeterminate to match, and re-enabled
# the claim check. Independent OCR of that back photo contains no "Limca"
# anywhere -- the only brand token is "COLA COMPANY" from the trademark line.
# The brand was invented.
#
# So an identity anchor is corroborated the same way an INS number is: against
# a reader that is not the model. Same asymmetry, for the same reason --
# finding the string is evidence, failing to find it is not, because Tesseract
# misses things constantly on curved photographed labels. Hence three states,
# and only OCR_CONTRADICTS downgrades.

CORROBORATED = "corroborated"
NOT_FOUND = "not_found_by_ocr"
OCR_UNUSABLE = "ocr_unusable"

# Below this many characters the OCR read is too poor to conclude anything
# from an absence.
_MIN_USABLE_CHARS = 60


def corroborate(image_bytes, needle):
    """Did an independent reader see this string on this face?"""
    if not needle or not (AVAILABLE or _cloud()):
        return OCR_UNUSABLE
    text = read_text(image_bytes) or ""
    if len(text.strip()) < _MIN_USABLE_CHARS:
        return OCR_UNUSABLE
    hay = re.sub(r"[^a-z0-9]", "", text.lower())
    pin = re.sub(r"[^a-z0-9]", "", str(needle).lower())
    if not pin:
        return OCR_UNUSABLE
    return CORROBORATED if pin in hay else NOT_FOUND


def check_identity_anchors(vision, front_bytes, back_bytes):
    """
    Corroborate the identity fields that product_match rests on.

    Returns (downgrade: bool, report: dict). downgrade is True only when OCR
    read the face well AND the claimed brand is absent from it -- i.e. positive
    evidence the value was invented, not mere failure to confirm.
    """
    # BACK FACE ONLY, deliberately.
    #
    # A front-of-pack brand is a stylised logo -- Limca's is white script on a
    # red ribbon -- and Tesseract cannot read logo type at any image quality.
    # Testing the front produced not_found_by_ocr for a brand occupying a third
    # of the photo, which would downgrade nearly every genuine scan.
    #
    # A back-of-pack brand, by contrast, comes from printed body text: a
    # manufacturer block, a trademark line, a legal footer. That is exactly
    # what OCR reads best, so an absence there carries real information.
    report, downgrade = {}, False
    report["front"] = {"brand": (vision.get("front_identity") or {}).get("brand"),
                       "status": "not_checked_logo_type"}

    # Corroborate BOTH fields _verified_anchors will accept, not just brand.
    #
    # The gap this closes: _verified_anchors counts a NAME match on both faces
    # as an identity anchor, but only brand was being corroborated. So a
    # hallucinated name appearing on both faces would unlock the claim check
    # with nothing checking it. Not hypothetical - on one run the model
    # returned product name "Carbonated Water", the first ingredient, for a
    # pack whose back carries no product name at all.
    back = vision.get("back_identity") or {}
    for field in ("brand", "name"):
        value = back.get(field)
        key = "back" if field == "brand" else "back_name"
        if not value or not back_bytes:
            report[key] = {"brand": value, "field": field, "status": "not_applicable"}
            continue
        status = corroborate(back_bytes, value)
        report[key] = {"brand": value, "field": field, "status": status}
        if status == NOT_FOUND:
            downgrade = True
    return downgrade, report

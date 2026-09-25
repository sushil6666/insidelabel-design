"""
Inside Label — API (v0.1)

    POST /analyze      raw ingredient text  -> layered verdict (engine verbatim)
    POST /claim-check  text + front claims  -> verdict + claim contradictions
    GET  /health

    POST /scan         one or two images   -> verdict + identity + claim check

THE GUARD THAT MATTERS
----------------------
engine.analyze("") returns score 100, grade A, binary "clean". That is correct
behaviour for the engine — no flagged ingredients means no penalties — but it
is the single most dangerous output this API can emit, because "we could not
read the label" and "this product is clean" become indistinguishable to the
user. Every path into the engine therefore refuses input that yields no usable
ingredient tokens, rather than passing an empty list through and letting a
false CLEAN out the door.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional  # noqa: E402

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

import engine  # noqa: E402
from app import claims as claim_checker  # noqa: E402
from app import reliability as rel  # noqa: E402
from app.vision import gemini  # noqa: E402
from app.vision import ocr_check  # noqa: E402
from app.schemas import (  # noqa: E402
    AnalyzeRequest,
    AnalyzeResponse,
    ClaimCheckRequest,
    ClaimCheckResponse,
)

ENGINE_VERSION = "0.1"

app = FastAPI(
    title="Inside Label API",
    version="0.1.0",
    description=(
        "Ingredient-list analysis. The engine states ingredient facts only — "
        "it never says a product is safe for any person or condition. Segment "
        "lenses sit above this API, not inside it."
    ),
)


# ---------------------------------------------------------------------------
def guard_ingredients(raw: str) -> None:
    """
    Refuse input the engine would score as a perfect 100 for the wrong reason.
    Raises HTTPException(422). Does not touch the engine or its thresholds.
    """
    if not raw or not raw.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "empty_ingredients",
                "detail": "raw_ingredients is empty.",
                "hint": "An empty list scores 100/100 CLEAN. Refused rather than returned.",
            },
        )
    if not engine.tokenize(raw):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_ingredient_tokens",
                "detail": "No ingredient tokens could be parsed from the input.",
                "hint": "An unparseable list scores 100/100 CLEAN. Refused rather than returned.",
            },
        )


# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "additives_loaded": len(engine._ADDITIVE_BY_INS),
        "nova_markers_loaded": len(engine.NOVA["markers"]),
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Wrap engine.analyze(). The verdict is returned exactly as the engine built it."""
    guard_ingredients(req.raw_ingredients)
    return {
        "verdict": engine.analyze(req.raw_ingredients),
        "engine_version": ENGINE_VERSION,
    }


@app.post("/claim-check", response_model=ClaimCheckResponse)
def claim_check(req: ClaimCheckRequest):
    """
    Text-only claim checking. Exists so the claim rules can be exercised
    against real labels without spending a vision call per iteration; /scan
    will call the same claim_checker.check_claims().
    """
    guard_ingredients(req.raw_ingredients)
    if req.front_status not in ("read", "not_provided", "unreadable"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "bad_front_status",
                "detail": 'front_status must be "read", "not_provided", or "unreadable".',
            },
        )
    verdict = engine.analyze(req.raw_ingredients)
    return {
        "verdict": verdict,
        "claim_check": claim_checker.check_claims(
            req.front_claims, req.raw_ingredients, verdict, req.front_status
        ),
        "engine_version": ENGINE_VERSION,
    }


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code, content={"error": "request_error", "detail": str(detail)}
    )


# ---------------------------------------------------------------------------
MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


async def _read_image(upload, role):
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail={
            "error": "image_too_large",
            "detail": f"{role} image is {len(data)} bytes; limit is {MAX_IMAGE_BYTES}.",
        })
    mime = upload.content_type or "image/jpeg"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail={
            "error": "unsupported_image_type",
            "detail": f"{role} image content_type {mime!r} is not supported.",
        })
    return (data, mime, role)


@app.post("/scan")
async def scan(
    back: Optional[UploadFile] = File(None, description="Back of pack — the ingredient list."),
    front: Optional[UploadFile] = File(None, description="Front of pack — marketing claims."),
    pairing_confirmed: bool = Form(False, description="User confirms both images show the same pack."),
    replay: Optional[str] = Form(None, description="Recorded model JSON, for testing without an API call."),
):
    """
    images -> Gemini -> engine -> claim check.

    The back of pack is the only required input: it carries the ingredient
    list, which is the only thing the engine can reason about. The front is
    optional and only enables the claim check.
    """
    images = []
    for upload, role in ((back, "back"), (front, "front")):
        img = await _read_image(upload, role)
        if img:
            images.append(img)

    if not images and replay is None:
        raise HTTPException(status_code=422, detail={
            "error": "no_images",
            "detail": "Supply at least a back-of-pack image.",
        })

    try:
        vision, corrections = gemini.analyze_images(images, raw_response=replay)
    except gemini.VisionUnavailable as e:
        # 503 with Retry-After, not 502. The images were fine and the request
        # was fine; the upstream model was busy. A client should retry this,
        # and a user should not be told their photo failed.
        raise HTTPException(status_code=503, detail={
            "error": "vision_unavailable",
            "detail": str(e),
            "retryable": True,
            "hint": "Model overloaded upstream. Already retried with backoff; try again shortly.",
        })
    except gemini.VisionError as e:
        raise HTTPException(status_code=502, detail={
            "error": "vision_failed", "detail": str(e), "retryable": False,
        })

    # Independent OCR cross-check on the back of pack. This is the only check
    # in the pipeline that is not the model grading itself, and it is the only
    # one that has ever caught a silent omission.
    back_bytes = next((d for d, _m, r in images if r == "back"), None)
    ocr_result = {"available": False, "reason": "no back image"}
    if back_bytes and vision.get("ingredients"):
        fixed, ocr_result, recovered = ocr_check.recover_entries(
            back_bytes, vision["ingredients"])
        if recovered:
            corrections.append(
                "independent OCR found additive(s) the model omitted: "
                + ", ".join(f"INS {i}" for i in ocr_result["missing"])
                + " — recovered as: " + "; ".join(recovered)
            )
            vision["ingredients"] = fixed

    # Corroborate the identity anchors product_match rests on against an
    # independent reader. A brand the model reports on a face where OCR read
    # the text well and found no such string was invented, and must not be
    # allowed to unlock the claim check.
    front_bytes = next((d for d, _m, r in images if r == "front"), None)
    _dg, _idrep = ocr_check.check_identity_anchors(vision, front_bytes, back_bytes)
    vision["_identity_corroboration"] = _idrep
    if _dg and (vision.get("product_match") or {}).get("status") == "match":
        bad = [f"{f}:{v['brand']!r}" for f, v in _idrep.items()
               if v["status"] == ocr_check.NOT_FOUND]
        corrections.append(
            "product_match downgraded to indeterminate — independent OCR read "
            "the face but found no such brand: " + ", ".join(bad)
        )
        vision["product_match"]["status"] = "indeterminate"
        vision["product_match"]["uncorroborated"] = bad
        # The anchors were computed from identity fields this check just
        # showed to be fabricated. Leaving them under verified_anchors would
        # display evidence supporting a match on a run downgraded precisely
        # because that evidence is not on the pack.
        vision["product_match"]["invalidated_anchors"] = \
            vision["product_match"].pop("verified_anchors", [])
        vision["verified_anchors"] = []
    vision["_ocr_cross_check"] = ocr_result

    vision["_pairing_attested_by_user"] = pairing_confirmed
    proceed, reliability = rel.assess(vision)
    reliability["client_corrections"] = corrections
    reliability["ocr_cross_check"] = {
        k: v for k, v in ocr_result.items() if k != "ocr_text"
    }
    if ocr_result.get("missing"):
        reliability["caveats"].append({
            "code": "model_omitted_additive",
            "detail": (
                "A second, independent OCR pass found "
                + ", ".join(f"INS {i}" for i in ocr_result["missing"])
                + " on the label that the vision model did not return. "
                "Recovered and included in the verdict."
            ),
        })

    if not proceed:
        return JSONResponse(status_code=422, content={
            "verdict": None,
            "product": vision.get("product"),
            "reliability": reliability,
            "engine_version": ENGINE_VERSION,
        })

    # The engine takes label-shaped text, and its tokenizer already handles
    # commas and brackets. Rejoining is deliberate: it keeps a single parsing
    # path for /analyze and /scan, so the two endpoints can never disagree.
    raw = ", ".join(vision["ingredients"])
    guard_ingredients(raw)
    verdict = engine.analyze(raw)

    return {
        "product": vision.get("product"),
        "verdict": verdict,
        "display": rel.apply_display_rule(verdict, reliability),
        "claim_check": claim_checker.check_claims(
            vision.get("front_claims", []), raw, verdict,
            # An unverified pairing suppresses the claim check the same way an
            # unread front does: in both cases we cannot say these claims
            # belong to this ingredient list.
            vision["front_status"] if reliability.get("claims_permitted", True)
            else "pairing_unverified",
        ),
        "extracted": {
            "ingredients": vision["ingredients"],
            "ingredients_status": vision["ingredients_status"],
            "front_claims": vision.get("front_claims", []),
            "front_claim_footnotes": vision.get("front_claim_footnotes", []),
            "allergen_statement": vision.get("allergen_statement"),
            "raw_text_sent_to_engine": raw,
        },
        "reliability": reliability,
        "disclosures": rel.disclosures(reliability),
        "engine_version": ENGINE_VERSION,
    }

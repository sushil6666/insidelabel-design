"""
Inside Label — reliability gate.

Sits between the vision layer and the engine and answers one question: given
how well the label was actually read, is a verdict safe to put in front of a
person?

It never touches the verdict. engine.analyze() output passes through exactly as
the engine built it; this module returns a sibling object saying how much of it
can be trusted, and refuses outright in the cases where any verdict at all
would be a lie.

The asymmetry that drives rule 3: a partially-read ingredient list can only
ever cause the engine to flag TOO LITTLE. Nothing you failed to read can add a
flag. So on a partial read, "ultra-processed" is still true — the markers found
are really there — but "clean" is unsupported, because the evidence that would
have overturned it is exactly the evidence you could not read.
"""

# (back_status, ingredients_status) -> hard refusal reason
_REFUSE = {
    "not_found": "no_ingredient_list_found",
    "unreadable": "ingredient_list_unreadable",
}


# D-103: what the model says each photo shows. The model reads; these rules
# decide. A photo of a screen is refused even when an ingredient list is
# legible on it: a listing or a picture on a display is a lead, never the
# record (D-089). Refusals for these codes can't go to "Send it to us".
NOT_A_PACK = ("back_is_a_screen", "not_a_food_pack")


def drop_unusable_front(vision):
    """
    A front photo that isn't a food pack is dropped, not fatal: the back still
    carries the ingredient list. Mutates `vision`; returns a caveat or None.
    """
    seen = (vision.get("image_content") or {}).get("front")
    if seen not in ("screen", "not_food"):
        return None
    vision["front_status"] = "not_provided"
    vision["front_claims"], vision["front_claim_footnotes"] = [], []
    vision["front_identity"] = None
    vision["product_match"] = {"status": "single_image", "evidence": []}
    return {"code": "front_not_a_pack",
            "detail": "The front photo doesn't show a food pack"
                      + (" (it looks like a screen)" if seen == "screen" else "")
                      + ", so it wasn't used."}


def assess(vision):
    """
    Returns (proceed: bool, reliability: dict).
    When proceed is False, reliability["error"] carries a machine-readable code.
    """
    back = vision["back_status"]
    ing = vision["ingredients_status"]
    front = vision["front_status"]

    # 0. Not a pack at all (D-103): say so, instead of "retake the photo".
    seen = (vision.get("image_content") or {}).get("back")
    if seen == "screen":
        return False, {
            "error": "back_is_a_screen",
            "detail": "The back photo shows a screen, not the pack itself.",
            "hint": "Photograph the physical pack; a listing or a picture on a screen isn't used.",
        }
    if seen == "not_food":
        return False, {
            "error": "not_a_food_pack",
            "detail": "The back photo doesn't show a packaged food.",
            "hint": "Photograph the ingredient list on the back of a food pack.",
        }

    # 1. No usable ingredient list -> no verdict, at all.
    # Two different products is a user error worth naming, not something to
    # silently analyse half of.
    if (vision.get("product_match") or {}).get("status") == "mismatch":
        ev = (vision.get("product_match") or {}).get("evidence") or []
        return False, {
            "error": "product_mismatch",
            "detail": "The two images appear to show different products."
                      + (" Evidence: " + "; ".join(ev) if ev else ""),
            "hint": "Photograph the front and back of the same pack, or send the back alone.",
            "front_identity": vision.get("front_identity"),
            "back_identity": vision.get("back_identity"),
        }

    if back != "read":
        return False, {
            "error": "back_not_read",
            "detail": f"back_status is {back}.",
            "hint": "A verdict needs the ingredient list. Retake the back of pack.",
        }
    if ing in _REFUSE:
        return False, {
            "error": _REFUSE[ing],
            "detail": f"ingredients_status is {ing}.",
            "hint": "Retake the back of pack with the ingredient list in frame and in focus.",
        }
    if not vision["ingredients"]:
        return False, {
            "error": "no_ingredients_extracted",
            "detail": "Ingredient array is empty.",
            "hint": "An empty list scores 100/100 CLEAN. Refused rather than returned.",
        }

    # 2. Partial read -> verdict returned, but a CLEAN result is not displayable.
    complete = ing == "read"
    reliability = {
        "error": None,
        "ingredients_complete": complete,
        "verdict_safe_to_display": True,
        "caveats": [],
        "extraction_notes": vision.get("extraction_notes", []),
        "confidence": vision.get("confidence", {}),
    }

    if not complete:
        reliability["verdict_safe_to_display"] = False
        reliability["caveats"].append({
            "code": "partial_ingredient_list",
            "detail": (
                "Part of the ingredient list could not be read. Missing "
                "ingredients can only add flags, never remove them, so a "
                "'clean' or high score here is unsupported. Flags that were "
                "found are still real."
            ),
        })

    # 3. Agreement across repeated reads. NOT the model's self-reported
    #    confidence: measured on 5 runs of one label, the model returned
    #    confidence 1.0 on every run including the two that silently dropped a
    #    printed preservative. Self-report carries no information about whether
    #    this particular read was complete, so gating on it was theatre.
    #
    #    consensus_meta comes from gemini.analyze_images_consensus(). When it is
    #    absent the scan was a single call, and that is itself worth saying.
    meta = vision.get("_consensus")
    if not meta:
        reliability["caveats"].append({
            "code": "single_read",
            "detail": (
                "Verdict built from one pass over the label. Repeat reads of the "
                "same image have been observed to differ by a full grade band."
            ),
        })
    elif not meta.get("unanimous"):
        n = meta["runs"]
        worst = min(meta["unstable"].values())
        reliability["caveats"].append({
            "code": "unstable_extraction",
            "detail": (
                f"{len(meta['unstable'])} ingredient(s) appeared in only some of "
                f"{n} reads (lowest {worst}/{n}): "
                + "; ".join(sorted(meta["unstable"]))
            ),
        })
        # An ingredient seen in a minority of reads is not solid enough to
        # carry a reassuring verdict.
        if worst * 2 <= n:
            reliability["verdict_safe_to_display"] = False

    # 3c. Cross-face identity decides whether claims may be checked at all.
    #
    #     The asymmetry that matters: a VERDICT needs only the back of pack,
    #     because the ingredient list is self-contained. A CLAIM CHECK needs
    #     both faces to belong to the same product, because it asserts that
    #     THIS pack's front contradicts THIS pack's ingredients. So an
    #     unverified pairing does not block the verdict — it blocks only the
    #     claim check.
    match = (vision.get("product_match") or {}).get("status", "indeterminate")
    reliability["product_match"] = match

    # A user confirming "yes, these are two faces of the same pack" supplies
    # the one piece of evidence that is genuinely absent from two still
    # photos. It is not a disclaimer -- it changes who is asserting the
    # pairing, and the claim check is conditional on it rather than on our
    # inference. Recorded explicitly so any output can say so.
    attested = bool(vision.get("_pairing_attested_by_user"))
    reliability["pairing_attested_by_user"] = attested
    reliability["claims_permitted"] = (
        match in ("match", "single_image") or (match == "indeterminate" and attested)
    )
    # Never let attestation override positive evidence of a mismatch. A user
    # can supply information we lack; they cannot overrule what we can see.

    if match == "indeterminate" and attested:
        reliability["caveats"].append({
            "code": "pairing_user_attested",
            "detail": (
                "Nothing on the pack independently confirms these two photos "
                "show the same product. Claims were checked on your confirmation "
                "that they do."
            ),
        })
    elif match == "indeterminate":
        reliability["caveats"].append({
            "code": "product_pairing_unverified",
            "detail": (
                "Nothing on the back of pack identifies which product it belongs "
                "to, so the two photos could not be confirmed as the same item. "
                "The ingredient verdict stands on its own; front-of-pack claims "
                "were not checked against it."
            ),
        })

    # 3d. The independent OCR cross-check is the only omission detector in the
    #     pipeline. Measured on one clean label, the vision model dropped a
    #     printed preservative in roughly 4 of 10 reads, and every self-check
    #     (confidence, raw declaration, self-count) reported success on those
    #     reads. So running WITHOUT the cross-check is running with a known,
    #     unmitigated omission rate — that is a caveat, not a footnote, and a
    #     reassuring score must not be presented as if it were verified.
    ocr = vision.get("_ocr_cross_check") or {}
    if ocr and not ocr.get("available"):
        reliability["caveats"].append({
            "code": "no_independent_verification",
            "detail": (
                "The independent OCR cross-check did not run ("
                + str(ocr.get("reason", "unknown"))
                + "). Nothing here can detect an additive the vision model "
                  "silently omitted. Install tesseract-ocr and pytesseract."
            ),
        })
        reliability["verdict_safe_to_display"] = False

    # 4. Front state drives the claim check, and is recorded whether or not it
    #    was read, so the caller never has to infer it.
    reliability["front_status"] = front
    if front != "read":
        reliability["caveats"].append({
            "code": f"front_{front}",
            "detail": (
                "Front-of-pack claims were not checked. This is not the same as "
                "finding no contradictions."
            ),
        })

    return True, reliability


def apply_display_rule(verdict, reliability):
    """
    Returns what the CLIENT should show, without mutating the verdict.

    The engine's own binary stays in `verdict.binary` untouched. This adds a
    separate `display_binary` which is the only thing a UI should render.
    """
    if reliability.get("verdict_safe_to_display", True):
        return {"display_binary": verdict["binary"], "display_score": verdict["score"]}

    # Suppress only the reassuring direction. An ultra-processed call on a
    # partial read is still supported by the markers that were read.
    if verdict["binary"] == "ultra-processed":
        return {"display_binary": "ultra-processed", "display_score": None}
    return {"display_binary": "incomplete", "display_score": None}


# ---------------------------------------------------------------------------
# User-facing disclosures
# ---------------------------------------------------------------------------
# Written here rather than in the client so every surface says the same thing,
# and so a limitation cannot be quietly dropped by a UI that ran out of room.
#
# These cover SCOPE -- what was and was not examined. They are not a substitute
# for a gate: no wording here makes it acceptable to assert that a named
# brand's claim is contradicted when the pairing is unproven. Disclaimers
# reduce misunderstanding; they do not make a false statement about a company
# harmless.

_DISCLOSURE_TEXT = {
    "single_read": "The label was read once. A second reading can differ.",
    "partial_ingredient_list": "Part of the ingredient list could not be read, so this may miss ingredients. Anything flagged is really there.",
    "no_independent_verification": "The second, independent check of the ingredient list did not run.",
    "model_omitted_additive": "An independent check found an additive the first reading missed. It has been included.",
    "product_pairing_unverified": "These two photos could not be confirmed as the same product, so front-of-pack claims were not checked.",
    "pairing_user_attested": "Front-of-pack claims were checked on your confirmation that both photos show the same product.",
    "front_not_provided": "No front of pack, so marketing claims were not checked.",
    "front_unreadable": "The front of pack could not be read, so marketing claims were not checked.",
    "unstable_extraction": "Repeated readings of this label disagreed about some ingredients.",
}

ALWAYS_DISCLOSE = [
    "This looks only at the ingredient list. Sugar, salt and fat quantities on the nutrition panel are not part of the score.",
    "Ingredients not yet in the database are not flagged, so an absence of flags is not proof of absence.",
    "Ingredient facts only. This is not advice about whether a food is right for you.",
]


def disclosures(reliability):
    """Plain-language notes for display, most specific first."""
    out = []
    for c in reliability.get("caveats", []):
        text = _DISCLOSURE_TEXT.get(c.get("code"))
        if text:
            out.append(text)
    return out + ALWAYS_DISCLOSE

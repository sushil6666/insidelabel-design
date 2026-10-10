#!/usr/bin/env python3
"""
Run label images through the real prompt + schema and write an eval-ready
prediction file.

    python3 tools/scan_label.py --id limca-pet-1l \
        --back photos/limca-back.png \
        --front photos/limca-front.png \
        --out predictions/

Then score it against the gold transcription:

    python3 tools/eval_vision.py --gold gold/ --pred predictions/

This is deliberately not the same as a quick "read this label" script. It sends
VISION_PROMPT with response_schema attached, so what comes back is the
structured object the engine consumes - not a sentence. A script that returns
prose has tested your API key and nothing else.
"""

import argparse
import json
import mimetypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.core import engine  # noqa: E402
from insidelabel.claims import checker as claim_checker  # noqa: E402
from insidelabel.reliability import gates as rel  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.extraction.providers import ocr_check  # noqa: E402

# Introductory rates for gemini-3.6-flash per Google Cloud, USD per 1M tokens,
# stated as running through 31 Dec 2026 with standard rates of 1.50/7.50 after.
# Sources disagree on whether the introductory or standard rate is live now, so
# treat the figure printed below as an ORDER OF MAGNITUDE, not a bill. The
# token counts beside it are measured and exact.
RATE_IN, RATE_OUT = 0.75, 3.75


def load(path, role):
    if not path:
        return None
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return (f.read(), mime, role)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="Stem for the output file; must match the gold file.")
    ap.add_argument("--back", required=True, help="Back of pack - the ingredient list.")
    ap.add_argument("--front", default=None, help="Front of pack - marketing claims.")
    ap.add_argument("--out", default="predictions")
    ap.add_argument("--raw", default=None, help="Also dump the unhardened model response here.")
    ap.add_argument("--pairing-confirmed", action="store_true",
                    help="Stand in for the user confirming both photos show the same pack.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    images = [i for i in (load(args.back, "back"), load(args.front, "front")) if i]

    def _note(attempt, delay, err):
        print(f"  upstream busy (attempt {attempt}) - retrying in {delay:.1f}s",
              file=sys.stderr)

    try:
        vision, corrections = gemini.analyze_images(images, on_attempt=_note)
    except gemini.VisionUnavailable as e:
        print(f"upstream unavailable, not your images or your key: {e}", file=sys.stderr)
        sys.exit(3)
    except gemini.VisionError as e:
        print(f"vision failed: {e}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(args.out, exist_ok=True)
    pred_path = os.path.join(args.out, f"{args.id}.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(vision, f, ensure_ascii=False, indent=2)

    if args.raw:
        os.makedirs(os.path.dirname(args.raw) or ".", exist_ok=True)
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump({"vision": vision, "client_corrections": corrections}, f, indent=2)

    # ---- ALL VERIFICATION RUNS BEFORE ANYTHING IS DISPLAYED ----
    # Previously the OCR cross-check and the identity corroboration sat below
    # the print statements, so a downgrade was computed after the pre-downgrade
    # status had already been shown, and its correction never reached the
    # CLIENT CORRECTIONS block. Output showed "match" on a run the code had
    # already decided was indeterminate. Verify, then print.
    back_bytes = next((d for d, _m, r in images if r == "back"), None)
    front_bytes = next((d for d, _m, r in images if r == "front"), None)

    ocr_res, recovered = {"available": False, "reason": "no back image"}, []
    if back_bytes and vision.get("ingredients"):
        fixed, ocr_res, recovered = ocr_check.recover_entries(
            back_bytes, vision["ingredients"])
        if recovered:
            vision["ingredients"] = fixed
            corrections.append(
                "independent OCR found additive(s) the model omitted: "
                + ", ".join(f"INS {i}" for i in ocr_res["missing"])
                + " - recovered as: " + "; ".join(recovered))
    vision["_ocr_cross_check"] = ocr_res

    _dg, _idrep = ocr_check.check_identity_anchors(vision, front_bytes, back_bytes)
    vision["_identity_corroboration"] = _idrep
    if _dg and (vision.get("product_match") or {}).get("status") == "match":
        bad = [f"{f}:{v['brand']!r}" for f, v in _idrep.items()
               if v["status"] == ocr_check.NOT_FOUND]
        corrections.append(
            "product_match downgraded to indeterminate - independent OCR read "
            "the back label but found no such brand on it: " + ", ".join(bad))
        vision["product_match"]["status"] = "indeterminate"
        vision["product_match"]["uncorroborated"] = bad
        # The anchors were computed from identity fields this check just
        # showed to be fabricated. Leaving them under verified_anchors would
        # display evidence supporting a match on a run downgraded precisely
        # because that evidence is not on the pack.
        vision["product_match"]["invalidated_anchors"] = \
            vision["product_match"].pop("verified_anchors", [])
        vision["verified_anchors"] = []

    vision["_pairing_attested_by_user"] = args.pairing_confirmed
    proceed, reliability = rel.assess(vision)

    if args.quiet:
        print(pred_path)
        return

    print(f"\nwrote {pred_path}")

    if corrections:
        print("\nCLIENT CORRECTIONS - the model's self-report was overridden:")
        for c in corrections:
            print(f"  - {c}")

    u = vision.get("_usage") or {}                                      # D-193: this call's own
    if u.get("total_tokens"):
        cost = ((u.get("input_tokens") or 0) * RATE_IN
                + (u.get("output_tokens") or 0) * RATE_OUT) / 1_000_000
        print(f"\ntokens     in={u.get('input_tokens')} out={u.get('output_tokens')} "
              f"thinking={u.get('thinking_tokens')} total={u.get('total_tokens')}")
        print(f"           ~${cost:.4f} per scan at intro rates "
              f"(~${cost*1000:.2f} per 1,000 scans)")

    print(f"\nstatuses   front={vision['front_status']}  back={vision['back_status']}  "
          f"ingredients={vision['ingredients_status']}")
    print(f"confidence {vision['confidence']}")

    pm = vision.get("product_match") or {}
    print(f"\nPRODUCT MATCH: {pm.get('status')}")
    for a in pm.get("verified_anchors", []):
        print(f"  anchor  : {a}")
    for a in pm.get("invalidated_anchors", []):
        print(f"  INVALIDATED anchor: {a}   (identity field not corroborated on the pack)")
    for e in pm.get("evidence_rejected", []):
        print(f"  rejected: {e}   (not an identity anchor)")
    fi, bi = vision.get("front_identity") or {}, vision.get("back_identity") or {}
    print(f"  front face: brand={fi.get('brand')!r} name={fi.get('name')!r}")
    print(f"  back face : brand={bi.get('brand')!r} mfr={bi.get('manufacturer')!r} "
          f"fssai={bi.get('fssai_licence')!r}")

    stated, actual = vision.get("ingredient_count"), len(vision.get("ingredients") or [])
    if isinstance(stated, int):
        flag = "" if stated == actual else "   <-- MISMATCH"
        print(f"\ncount: model said {stated}, returned {actual}{flag}")

    if vision.get("ingredient_lines"):
        print("\nPRINTED LINES (source of truth)")
        for i, l in enumerate(vision["ingredient_lines"], 1):
            print(f"  {i}. {l}")

    print("\nINDEPENDENT OCR CROSS-CHECK")
    if not ocr_res.get("available"):
        print(f"  !! UNAVAILABLE: {ocr_res.get('reason')}")
        print("  !!    sudo apt install tesseract-ocr && pip install pytesseract")
    else:
        print(f"  OCR found   : {ocr_res['ocr_ins']}")
        print(f"  model found : {ocr_res['model_ins']}")
        print(f"  {'MODEL OMITTED: ' + str(ocr_res['missing']) + ' -> recovered ' + str(recovered) if recovered else 'agreement on all INS numbers'}")
    ident = vision.get("_identity_corroboration") or {}
    if ident:
        print("  identity corroboration:")
        for face, r in ident.items():
            print(f"    {face:6} brand={r['brand']!r} -> {r['status']}")

    print(f"\nINGREDIENTS ({len(vision['ingredients'])} entries)")
    for i, x in enumerate(vision["ingredients"], 1):
        print(f"  {i:>2}. {x}")

    if vision.get("front_claims"):
        print("\nFRONT CLAIMS")
        for x in vision["front_claims"]:
            print(f"  - {x}")

    if vision.get("extraction_notes"):
        print("\nEXTRACTION NOTES")
        for x in vision["extraction_notes"]:
            print(f"  - {x}")

    if not proceed:
        print(f"\nNO VERDICT: {reliability['error']} - {reliability['detail']}")
        return

    raw = ", ".join(vision["ingredients"])
    verdict = engine.analyze(raw)
    print()
    print(engine.render(verdict))
    print(f"\ndisplay: {rel.apply_display_rule(verdict, reliability)}")

    # An unverified pairing suppresses the claim check exactly as an unread
    # front does - /scan already did this; the CLI did not, and reported
    # "checked" on a scan whose two faces were never confirmed to be the same
    # product. Two entry points disagreeing about a safety gate is worse than
    # either behaviour on its own.
    cc = claim_checker.check_claims(
        vision.get("front_claims", []), raw, verdict,
        vision["front_status"] if reliability.get("claims_permitted", True)
        else "pairing_unverified",
    )
    notes = rel.disclosures(reliability)
    if notes:
        print("\nWHAT THIS DOES AND DOESN'T COVER")
        for n in notes:
            print(f"  • {n}")

    # Display-only. "checked" with nothing beneath it is ambiguous between
    # "no contradictions found" and "no rule covered any of these claims" -
    # and on the first real pack it meant the second. A claim checker that
    # silently examines nothing looks identical to one that cleared the pack.
    print(f"\nCLAIM CHECK: {cc['status']}" + (f" ({cc['reason']})" if cc["reason"] else ""))
    print(f"  claims examined: {cc['claims_examined']}   "
          f"rules matched: {len(cc['checked'])}   "
          f"no rule: {len(cc['unmatched_claims'])}")
    for ch in cc["checked"]:
        mark = "CONTRADICTED" if ch["contradicted"] else "no contradiction"
        print(f"  [{mark}] {ch['claim']}")
        for fact in ch["contradicted_by"]:
            print(f"      -> {fact['fact']}")
        for fact in ch.get("adjacent_facts", []):
            print(f"      (adjacent, not a contradiction) {fact['fact']}")
    for c in cc["unmatched_claims"]:
        print(f"  [NO RULE]      {c}")


if __name__ == "__main__":
    main()

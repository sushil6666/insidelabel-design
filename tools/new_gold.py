#!/usr/bin/env python3
"""
Create an EMPTY gold stub to transcribe by hand.

    python3 tools/new_gold.py --id britannia-nutrichoice

WHY THIS IS EMPTY
    It would be trivial to prefill this from the model's prediction and let you
    correct it. Do not. Gold built by editing model output agrees with the
    model by construction and measures nothing - you will accept whatever
    looked plausible and only catch the errors that happen to look wrong.

    Transcribe from the photo, blind, then run the eval. A disagreement is then
    real information instead of an artefact of where you started.

THE RULE THAT MATTERS
    For every field, be able to point at the pixels.

    Three gold errors were made on the first two labels of this project, all
    the same shape - writing what the pack MEANS rather than what it PRINTS:
      - net_quantity "2000 ml", derived by multiplying 200ml x 10 servings.
        The pack prints no total.
      - back_identity.brand "Limca", inferred because it is a Limca bottle.
        The back label carries no Limca wordmark at all.
      - product.name "Limca Lime 'N' Lemoni", assembled from a wordmark and a
        separate descriptor. That string appears nowhere on the pack.

    Each is a reasonable description of the product and none is a
    transcription. If you cannot point at it, the value is null and the reason
    goes in extraction_notes.
"""

import argparse
import json
import os

STUB = {
    "front_status": "read",
    "back_status": "read",
    "ingredients_status": "read",
    "product": {
        "brand": None,
        "name": None,
        "variant": None,
        "net_quantity": None,
        "veg_mark": "not_visible",
    },
    "product_match": {
        "status": "indeterminate",
        "evidence": [],
    },
    "front_identity": {"brand": None, "name": None, "manufacturer": None},
    "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
    "ingredient_lines": [],
    "ingredient_count": 0,
    "ingredients": [],
    "allergen_statement": None,
    "front_claims": [],
    "front_claim_footnotes": [],
    "extraction_notes": [],
    "confidence": {"ingredients": 1.0, "front_claims": 1.0, "product_identity": 1.0},
}

CHECKLIST = """
Transcribing {id} - work in this order, from the photos only:

  1. ingredient_lines   one entry per PRINTED LINE, copied exactly.
                        Keep INS numbers as printed: "(330, 331(iii))" stays
                        bare if the pack prints it bare.
  2. ingredient_count   count top-level commas, add one.
  3. ingredients        split the lines on top-level commas. Bracketed
                        sub-lists stay with their parent:
                        "Emulsifiers (INS 322, INS 471)" is ONE entry.
  4. product            brand / name / variant AS PRINTED, separately.
                        Never join them. net_quantity only if a total is
                        printed - do not compute it from serving size.
  5. front_claims       verbatim marketing claims only, asterisks included.
                        NOT: brand, product name, net quantity, MRP, price
                        stickers, FSSAI number, batch codes, veg mark,
                        "MADE IN INDIA", storage instructions.
  6. back_identity      only what is legible on the BACK. A parent-company
                        line ("A product of The Coca-Cola Company") is not a
                        brand and not a manufacturer.
  7. product_match      "match" ONLY with a specific shared identifier you can
                        see on both faces. Shared category or shared parent
                        company do not count. Default to "indeterminate".
  8. extraction_notes   every field you left null, and why.

Occluded, blurred or cut-off text: leave it out. Do not guess it.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--dir", default="gold")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    path = os.path.join(args.dir, f"{args.id}.json")
    if os.path.exists(path) and not args.force:
        print(f"{path} already exists. --force to overwrite (you will lose the transcription).")
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(STUB, f, ensure_ascii=False, indent=2)
    print(f"wrote {path}")
    print(CHECKLIST.format(id=args.id))


if __name__ == "__main__":
    main()

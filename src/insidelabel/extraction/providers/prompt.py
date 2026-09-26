"""
Inside Label — Gemini Flash vision layer: prompt + response schema.

This module is DATA, not logic. No API client here on purpose: the prompt is
the thing that determines whether every downstream verdict is built on real
label text or on a plausible hallucination, so it gets reviewed on its own
before any endpoint code wraps around it.

Architectural rule this prompt enforces:
    the vision model TRANSCRIBES. It never classifies, normalises, or judges.
    All normalisation is engine.py's job (normalization.json), all judgement is
    the engine's, all segment framing is the lens layer's. If the vision model
    expands "INS 471" into "mono- and diglycerides", the traceability promise
    ("here are the receipts") is broken at the first step and every layer above
    inherits an unsourceable fact.
"""

# A specific stable model name, NOT a "-latest" alias. Stable names point at a
# fixed model; -latest aliases get hot-swapped on each release, which would
# silently invalidate every eval number and every gold file measured against
# them.
#
# History: this was gemini-2.5-flash until Google closed it to new API keys
# with a 404 naming gemini-3.6-flash as the replacement. The lesson is that a
# stable model name is stable until the vendor retires it, so the model string
# is an operational dependency with a lifetime, not a constant.
#
# 3.6 Flash is a current stable model. Avoid 3.5-flash: a developer reported it
# intermittently 404ing to a decommissioned backing build, which surfaces as a
# 404 rather than a 429/503 and so is not caught by the retry logic.
#
# WHEN YOU CHANGE THIS, the eval baseline resets. Re-run every gold label
# against the new model before comparing any number to a previous run; the
# model string is stamped into each prediction file so a mixed-model
# predictions/ directory is detectable rather than silently averaged.
MODEL = "gemini-3.6-flash"

# Generation config to pass alongside the schema. Temperature 0: transcription
# has one correct answer, so there is nothing for sampling to help with.
# Gemini 3.x deprecated temperature / top_p / top_k and dropped
# candidate_count entirely. They are currently ignored rather than rejected,
# which is worse than an error: the sampling settings this file appeared to
# specify were never being applied on 3.x, and they may start returning HTTP
# 400 later. Removed rather than left as decoration.
#
# THINKING_LEVEL replaces the old thinking_budget. 3.6 Flash thinks by default,
# and thinking tokens bill at OUTPUT rates — the most expensive tokens there
# are. Transcribing an ingredient list needs no reasoning, so this is set as
# low as the API allows. Raise it only if the eval shows accuracy depends on it.
GENERATION_CONFIG = {
    "response_mime_type": "application/json",
    # "response_schema": VISION_RESPONSE_SCHEMA,  # wired in by the client
}

THINKING_LEVEL = "low"


VISION_PROMPT = """\
You are a label transcription system for Indian packaged food. You are given one \
or two photographs of a single product: the FRONT of pack, and the BACK of pack \
(the face carrying the ingredient list and the FSSAI panel).

Your only job is to TRANSCRIBE what is printed. You do not evaluate, classify, \
rate, or comment on the food. Code downstream of you does all of that.

Return a single JSON object matching the supplied schema. No prose, no markdown, \
no code fences, no text before or after the object.

RULES

1. TRANSCRIBE, NEVER NORMALISE.
   - Copy ingredient text exactly as printed: spelling, spacing, bracketed
     contents, percentages.
   - Keep INS / E numbers exactly as printed. "Emulsifiers (INS 322, INS 471)"
     stays in that form. Never expand a number into a chemical name. Never add
     a number to a named ingredient.
   - Keep Indian spellings as printed: Soya, Iodised, Colour, Maida, Vanaspati.
   - Do not correct printing or spelling errors. Do not translate. Do not
     reorder. Do not deduplicate.

2. NEVER INVENT.
   - If characters are unreadable, do not guess the word. Leave the entry out
     and say what was unreadable in extraction_notes.
   - An empty ingredients array with ingredients_status "unreadable" is a
     CORRECT answer. A plausible-looking guess is a WRONG answer.
   - Ingredients come from the printed ingredient list only. Never add one
     because it is typical for this kind of product, because it is named on the
     front of pack, or because the product name implies it.

3. TRANSCRIBE LINE BY LINE, AS PRINTED.
   - ingredient_lines is the ingredient declaration copied ONE PRINTED LINE AT
     A TIME, in order, exactly as the text is laid out on the pack. One array
     entry per physical line of print.
   - Copy each line and then move to the next. Do not read ahead, do not
     rephrase, do not merge lines, do not tidy line breaks away. A line that
     ends mid-word or mid-item is copied ending mid-word or mid-item.
   - This is a copying task, not a summarising task. You are reproducing marks
     on a surface, not restating what the product contains.
   - Then set ingredient_count to the number of separate ingredients you can
     count across those lines, counting top-level commas plus one. Count them;
     do not estimate. If your ingredients array does not have exactly
     ingredient_count entries, you have dropped or merged something — go back
     to ingredient_lines and fix the array.
   - Fill ingredient_lines FIRST, then ingredient_count, then the ingredients
     array. The array must contain every ingredient present in the lines and
     nothing absent from them.

4. INGREDIENT LIST BOUNDARIES (for the split array).
   - Begin at the "Ingredients" heading; stop at the end of that list.
   - Split on the TOP-LEVEL commas of the printed list only. Bracketed
     sub-lists stay attached to their parent:
        "Emulsifiers (INS 322, INS 471)"  -> ONE entry
        "Refined Wheat Flour (Maida)"     -> ONE entry
        "Cocoa Solids (12%)"              -> ONE entry, percentage kept
   - If the product has separate components (noodle cake + tastemaker, etc.),
     keep each printed component heading as its own entry, in place, exactly as
     printed (e.g. "Tastemaker:").
   - These are NOT ingredients: allergen statements, "may contain traces of",
     storage instructions, nutrition tables, marketing text, serving
     suggestions. Put an allergen statement in allergen_statement as printed;
     discard the rest.

5. FRONT-OF-PACK CLAIMS.
   - front_claims are the marketing claims printed on the front, VERBATIM,
     including capitalisation and any asterisk:
        "NO ADDED SUGAR*", "Made with Real Fruit", "100% Atta", "Zero Maida"
   - If the footnote an asterisk points to is legible, copy it as printed into
     front_claim_footnotes.
   - Do NOT include: brand name, product name, net weight, MRP, the green/brown
     veg mark, FSSAI licence number, batch or date codes, barcodes, customer
     care details, or serving suggestions.
   - Do not paraphrase, sentence-case, or tidy a claim. Copy it character for
     character. Downstream code quotes these back to the user verbatim.

6. IMAGE ROLES AND WHETHER THE FACES MATCH.
   - Decide which supplied image is front and which is back from their CONTENT,
     not from the order they were given in. A back-of-pack image carries the
     ingredient list or the nutrition panel.
   - If both images show the same face, use the more legible one and note the
     duplicate in extraction_notes.

   - When two images are supplied, decide whether they show THE SAME PRODUCT
     and set product_match.status:
       "match"          positive evidence they are the same product
       "mismatch"       positive evidence they are DIFFERENT products
       "indeterminate"  no usable identifying evidence either way
     List the specific evidence you used in product_match.evidence.

   - Evidence that counts: the same brand wordmark on both faces; the same
     product name; the same FSSAI licence number; the same manufacturer NAME
     AND ADDRESS from a "Manufactured by" / "Marketed by" block.

   - Evidence that does NOT count, and must not be cited: a shared product
     category or type ("both are lemon drinks"); a shared parent company
     ("both are Coca-Cola products") — one company owns many different
     products; similar colours alone; the fact that the two images were
     supplied together.

   - manufacturer means the entity in a "Manufactured by" or "Marketed by"
     block, with its address. A trademark attribution ("X is a registered
     trademark of Y") names the trademark HOLDER, not the manufacturer —
     leave manufacturer null rather than filling it from a trademark line.

   - "match" requires POSITIVE evidence. Two images arriving together is not
     evidence. If the back of pack is a plain ingredient panel with no brand
     mark, no manufacturer block and no shared artwork, the honest answer is
     "indeterminate", not "match". Guessing "match" is the failure that lets
     one product's ingredients be reported under another product's name.

   - "mismatch" also requires positive evidence — two DIFFERENT brand names,
     two different manufacturers, two different licence numbers. Say what you
     saw.

   - Fill front_identity and back_identity separately with whatever brand,
     product name and manufacturer is legible on THAT face alone. Leave a
     field null if that face does not show it. Do not copy a value from one
     face to the other.

7a. WHAT EACH IMAGE SHOWS — DECIDE THIS FIRST (image_content).
   For image_content.back and image_content.front, say what the image is:
   - "food_pack": a photograph of a physical packaged food or drink, or of
     its label, taken directly (held in a hand, on a shelf, on a table).
   - "screen": a screenshot, or a photograph of a screen (phone, computer,
     TV): a shop website, an app, a picture of a pack shown on a display.
     Use "screen" even when a food pack or an ingredient list is visible on
     that screen.
   - "not_food": anything else: documents, software, people, rooms, a
     product that is not food or drink (cosmetics, cleaning products,
     medicines), a blank or unrecognisable image.
   - "not_provided": that image was not supplied.
   This describes the image, not the product. When the image is "screen" or
   "not_food", still set the statuses below honestly and transcribe nothing
   you cannot see printed on a physical pack.

7. MISSING OR UNREADABLE FACES — SET STATUS HONESTLY.
   - front_status:       "read" | "not_provided" | "unreadable"
   - back_status:        "read" | "not_provided" | "unreadable"
   - ingredients_status: "read" | "partial" | "not_found" | "unreadable"
   - Only a back image supplied -> front_status "not_provided", front_claims
     []. Still fill product identity from anything printed on the back; brand
     and product name usually repeat near the FSSAI panel.
   - Front supplied but glare, blur, crop or angle prevents reading it ->
     front_status "unreadable", front_claims []. Do NOT fall back to guessing
     claims from the product name or from the back of pack.
   - "partial" means you found the ingredient list but could not read all of
     it. Return what you could read and state precisely what is missing in
     extraction_notes (e.g. "last two entries obscured by fold").
   - "not_found" means no ingredient list is visible on the supplied images.
   - Never use "read" as a default. Use it only for something you actually
     read.

8. SAY NOTHING ABOUT HEALTH.
   - Do not describe any ingredient as safe, unsafe, natural, artificial,
     healthy, harmful, good, or bad, anywhere in your output.
   - extraction_notes are about image legibility and transcription gaps only.

9. CONFIDENCE.
   - Report confidence per field group as a number from 0.0 to 1.0, reflecting
     how certain you are that the characters you returned are the characters
     printed. Low confidence is useful information; inflated confidence is not.

EXAMPLE (fragment, to show entry splitting only)

Printed on back:
    INGREDIENTS: Refined Wheat Flour (Maida), Sugar, Edible Vegetable Oil
    (Palm), Invert Syrup, Emulsifiers (INS 322, INS 471), Raising Agents
    (INS 500(ii)), Iodised Salt, Added Flavours (Natural & Nature Identical).
    CONTAINS WHEAT AND MILK.

Correct ingredient_lines (one entry per printed line):
    ["INGREDIENTS: Refined Wheat Flour (Maida), Sugar, Edible Vegetable Oil",
     "(Palm), Invert Syrup, Emulsifiers (INS 322, INS 471), Raising Agents",
     "(INS 500(ii)), Iodised Salt, Added Flavours (Natural & Nature",
     "Identical)."]

Correct ingredient_count:
    8

Correct ingredients array:
    ["Refined Wheat Flour (Maida)", "Sugar", "Edible Vegetable Oil (Palm)",
     "Invert Syrup", "Emulsifiers (INS 322, INS 471)", "Raising Agents (INS
     500(ii))", "Iodised Salt", "Added Flavours (Natural & Nature Identical)"]

Correct allergen_statement:
    "CONTAINS WHEAT AND MILK."
"""


# Gemini responseSchema (OpenAPI 3.0 subset: no additionalProperties, no
# oneOf). Everything is required so the client never has to distinguish
# "the model omitted this" from "the model meant null" — an omitted status is
# exactly the ambiguity that produces a false "clean" verdict downstream.
_IMAGE_CONTENT = {
    "type": "string",
    "enum": ["food_pack", "screen", "not_food", "not_provided"],
}

VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "image_content": {
            "type": "object",
            "description": "What each image is (rule 7a): a food pack photographed directly, a screen, or something else.",
            "properties": {"back": _IMAGE_CONTENT, "front": _IMAGE_CONTENT},
            "required": ["back", "front"],
            "propertyOrdering": ["back", "front"],
        },
        "front_status": {
            "type": "string",
            "enum": ["read", "not_provided", "unreadable"],
            "description": "Whether the front of pack was actually read.",
        },
        "back_status": {
            "type": "string",
            "enum": ["read", "not_provided", "unreadable"],
            "description": "Whether the back of pack was actually read.",
        },
        "ingredients_status": {
            "type": "string",
            "enum": ["read", "partial", "not_found", "unreadable"],
            "description": (
                "read = whole list transcribed. partial = list found, some "
                "entries unreadable. not_found = no list visible. unreadable = "
                "list located but illegible."
            ),
        },
        "product_match": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["match", "mismatch", "indeterminate", "single_image"],
                    "description": "Whether both supplied faces are the same product. 'match' and 'mismatch' both require positive evidence.",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The specific things you saw that support the status.",
                },
            },
            "required": ["status", "evidence"],
            "propertyOrdering": ["status", "evidence"],
        },
        "front_identity": {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "nullable": True},
                "name": {
                    "type": "string",
                    "nullable": True,
                    "description": "Product name on this face only. Descriptors go in product.variant, not here.",
                },
                "manufacturer": {"type": "string", "nullable": True},
            },
            "required": ["brand", "name", "manufacturer"],
            "propertyOrdering": ["brand", "name", "manufacturer"],
        },
        "back_identity": {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "nullable": True},
                "name": {"type": "string", "nullable": True},
                "manufacturer": {"type": "string", "nullable": True},
                "fssai_licence": {"type": "string", "nullable": True},
            },
            "required": ["brand", "name", "manufacturer", "fssai_licence"],
            "propertyOrdering": ["brand", "name", "manufacturer", "fssai_licence"],
        },
        "product": {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "nullable": True},
                "name": {"type": "string", "nullable": True},
                "variant": {
                    "type": "string",
                    "nullable": True,
                    "description": (
                        "The flavour or sub-variant line as printed, e.g. 'Masala', "
                        "'Diabetic Friendly', \"Lime 'n' Lemoni\". Put the descriptor "
                        "HERE, not in name. Never join name and variant into one "
                        "string — a combined string appears nowhere on the pack."
                    ),
                },
                "net_quantity": {
                    "type": "string",
                    "nullable": True,
                    "description": "As printed with units, e.g. '75 g'.",
                },
                "veg_mark": {
                    "type": "string",
                    "enum": ["veg", "non_veg", "not_visible"],
                    "description": "The Indian green/brown square mark.",
                },
            },
            "required": ["brand", "name", "variant", "net_quantity", "veg_mark"],
            "propertyOrdering": ["brand", "name", "variant", "net_quantity", "veg_mark"],
        },
        "ingredient_lines": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "The ingredient declaration copied one printed line at a time, "
                "in layout order. Source of truth; fill this first."
            ),
        },
        "ingredient_count": {
            "type": "integer",
            "description": (
                "Number of separate ingredients counted across ingredient_lines "
                "(top-level commas plus one). The ingredients array must have "
                "exactly this many entries."
            ),
        },
        "ingredients": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Top-level ingredient entries, verbatim, in printed order.",
        },
        "allergen_statement": {"type": "string", "nullable": True},
        "front_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim front-of-pack marketing claims, asterisks included.",
        },
        "front_claim_footnotes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Legible asterisk footnote text, as printed.",
        },
        "extraction_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Legibility and transcription gaps only. Never health commentary.",
        },
        "confidence": {
            "type": "object",
            "properties": {
                "ingredients": {"type": "number"},
                "front_claims": {"type": "number"},
                "product_identity": {"type": "number"},
            },
            "required": ["ingredients", "front_claims", "product_identity"],
            "propertyOrdering": ["ingredients", "front_claims", "product_identity"],
        },
    },
    "required": [
        "image_content",
        "front_status",
        "back_status",
        "ingredients_status",
        "product",
        "product_match",
        "front_identity",
        "back_identity",
        "ingredient_lines",
        "ingredient_count",
        "ingredients",
        "allergen_statement",
        "front_claims",
        "front_claim_footnotes",
        "extraction_notes",
        "confidence",
    ],
    "propertyOrdering": [
        "image_content",
        "front_status",
        "back_status",
        "ingredients_status",
        "product",
        "product_match",
        "front_identity",
        "back_identity",
        "ingredient_lines",
        "ingredient_count",
        "ingredients",
        "allergen_statement",
        "front_claims",
        "front_claim_footnotes",
        "extraction_notes",
        "confidence",
    ],
}

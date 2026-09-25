#!/usr/bin/env python3
"""
Fetch Indian product records from Open Food Facts into a local JSONL fixture.

Run this on your machine, not in a sandbox — OFF is not reachable from the
Claude container.

    python3 tools/fetch_off.py --target 150 --out fixtures/off_india.jsonl

WHAT THIS IS FOR
    Validation input for engine.py. Not a product database. See the licence
    note at the bottom of this file before any of it goes near production.

WHAT IT DELIBERATELY DOES NOT DO
    It does not validate the vision layer. Every row here is text that someone
    already transcribed. Your hardest accuracy problem — reading a crumpled
    foil packet under shop lighting — is untouched by this dataset. You still
    have to photograph real packs for that.
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

# OFF asks every client to identify itself so they can get in touch if a
# script misbehaves. Put a real contact address here before running.
USER_AGENT = "InsideLabel/0.1 (validation harness) - contact: you@analyticswithsushil.com"

BASE = "https://in.openfoodfacts.org/api/v2/search"

FIELDS = ",".join([
    "code",
    "product_name",
    "brands",
    "quantity",
    "ingredients_text",
    "ingredients_text_en",
    "ingredients_text_debug",
    "additives_tags",        # OFF's own additive detection — the cross-check
    "nova_group",            # OFF's own NOVA classification — the benchmark
    "nutriscore_grade",
    "categories_tags",
    "labels_tags",           # sometimes carries front-of-pack claims
    "countries_tags",
    "lang",
    "states_tags",           # tells you if ingredients were completed or not
])

# Rate limiting: OFF publishes limits on the search endpoint and they change.
# At page_size=100 you need two requests for 150 products, so this is mostly
# courtesy. Check the current documented limit before raising --target a lot.
SLEEP_BETWEEN_PAGES = 6.0


def fetch_page(page, page_size, extra_params=None):
    params = {
        "fields": FIELDS,
        "page_size": str(page_size),
        "page": str(page),
        "countries_tags_en": "india",
    }
    if extra_params:
        params.update(extra_params)
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def best_ingredient_text(p):
    """
    Prefer the English field, fall back to the raw one. Returns None if there
    is nothing usable — which is the common case on Indian records, so we skip
    rather than feed the engine an empty string.
    """
    for key in ("ingredients_text_en", "ingredients_text"):
        t = (p.get(key) or "").strip()
        if t:
            return t
    return None


def usable(text, min_chars, min_commas):
    """
    Reject records that would produce a meaningless verdict.

    An ingredient list of "Wheat" is not a test case, it is a stub. An
    ingredient list that scores 100/100 because it is three words long tells
    you nothing about the engine and quietly inflates your CLEAN rate.
    """
    if not text or len(text) < min_chars:
        return False
    if text.count(",") < min_commas:
        return False
    # Records that are obviously still raw OCR junk
    if re.search(r"[^\x00-\x7F]{20,}", text):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=150,
                    help="How many usable products to collect.")
    ap.add_argument("--out", default="fixtures/off_india.jsonl")
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=25,
                    help="Safety stop. Indian records with ingredient text are "
                         "sparse, so expect to page well past target/page_size.")
    ap.add_argument("--min-chars", type=int, default=40)
    ap.add_argument("--min-commas", type=int, default=2)
    ap.add_argument("--category", default=None,
                    help="Optional categories_tags_en filter, e.g. 'biscuits'. "
                         "Useful for building a category-balanced set.")
    args = ap.parse_args()

    extra = {"categories_tags_en": args.category} if args.category else None

    kept, seen = [], set()
    scanned = skipped_no_text = skipped_stub = 0

    for page in range(1, args.max_pages + 1):
        try:
            data = fetch_page(page, args.page_size, extra)
        except Exception as e:                                   # noqa: BLE001
            print(f"  page {page} failed: {e}", file=sys.stderr)
            break

        products = data.get("products", [])
        if not products:
            break

        for p in products:
            scanned += 1
            code = p.get("code")
            if not code or code in seen:
                continue
            text = best_ingredient_text(p)
            if not text:
                skipped_no_text += 1
                continue
            if not usable(text, args.min_chars, args.min_commas):
                skipped_stub += 1
                continue
            seen.add(code)
            kept.append({
                "code": code,
                "product_name": p.get("product_name"),
                "brands": p.get("brands"),
                "quantity": p.get("quantity"),
                "ingredients_text": text,
                "off_additives_tags": p.get("additives_tags") or [],
                "off_nova_group": p.get("nova_group"),
                "off_nutriscore": p.get("nutriscore_grade"),
                "categories_tags": p.get("categories_tags") or [],
                "labels_tags": p.get("labels_tags") or [],
                "lang": p.get("lang"),
            })
            if len(kept) >= args.target:
                break

        print(f"  page {page}: scanned {scanned}, kept {len(kept)}", file=sys.stderr)
        if len(kept) >= args.target:
            break
        time.sleep(SLEEP_BETWEEN_PAGES)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nscanned            {scanned}", file=sys.stderr)
    print(f"no ingredient text {skipped_no_text}", file=sys.stderr)
    print(f"too short / stub   {skipped_stub}", file=sys.stderr)
    print(f"written            {len(kept)} -> {args.out}", file=sys.stderr)
    if len(kept) < args.target:
        print(f"\nShort of target. Indian records frequently carry photos but no "
              f"transcribed ingredient list; raise --max-pages or drop "
              f"--min-commas.", file=sys.stderr)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# LICENCE — read before this touches production
# ---------------------------------------------------------------------------
# Open Food Facts data is published under the Open Database License (ODbL),
# which carries a share-alike obligation on DERIVED DATABASES. For a product
# whose stated moat is its own data tables, the distinction that matters is:
#
#   Using these records as TEST INPUT to check whether engine.py's verdicts
#   hold up  ->  does not make additives.json a derived database. Your tables
#                stay yours.
#
#   Ingesting these records INTO an Inside Label product database that you
#   then ship  ->  that shipped database is plausibly a derived database, and
#                  share-alike would attach to it.
#
# The first is what this script is for. The second is a different decision and
# not one to drift into by accident. I'm not a lawyer — worth a real opinion
# before any OFF-sourced record ends up in a product catalog you sell access to.
# Attribution to Open Food Facts is required either way.

#!/usr/bin/env python3
"""
Run engine.py over an Open Food Facts fixture and report where it is wrong or
blind.

    python3 tools/coverage_report.py fixtures/off_india.jsonl \
        --csv reports/per_product.csv

WHY THIS EXISTS
    Downloading 150 products is the easy half. The README's step 2 is the one
    that matters: "note every wrong verdict and every ingredient it couldn't
    match". Eyeballing 150 rows will not do that reliably, and it gives you no
    number to point at.

    Each OFF record carries two things that make this a real test rather than a
    demo: `additives_tags`, which is OFF's OWN additive detection on the SAME
    ingredient text, and `nova_group`, which is OFF's own NOVA classification.
    Both were produced independently of your engine. So this is not the engine
    grading its own homework — it is two systems reading identical input, and
    every disagreement is a lead.

    The single most useful output is MISSED ADDITIVES: INS numbers OFF found in
    text your engine also parsed, but which your tables have no row for. That
    is a ranked, demand-driven to-do list for additives.json, in frequency
    order, derived from real Indian labels rather than guesswork.

WHAT IT CANNOT TELL YOU
    Nothing here validates OCR. Every row is pre-transcribed text. It also
    cannot tell you whether a *concern level* is right — OFF has no opinion on
    whether INS 951 is "moderate". That judgement stays yours and still needs
    human review against FSSAI.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from insidelabel.core import engine  # noqa: E402
from insidelabel.core.tokenize import extract_ins  # noqa: E402  (the one INS parser, D-099)

# OFF tags look like "en:e471" or "en:e160a". E-numbers and INS numbers are
# aligned for the vast majority of additives but they are not the same
# namespace — treat a match as a strong lead, not as proof.
_E_TAG = re.compile(r"^[a-z]{2}:(e\S+)$", re.IGNORECASE)      # the number itself goes to extract_ins

# Tokens that look like an additive the engine should have known, as opposed to
# a plain food it is right to ignore. Drives the miss triage.
_ADDITIVE_WORDS = re.compile(
    r"(emulsifier|preservative|colour|color|"
    r"stabilis|stabiliz|thickener|acidity|antioxidant|raising agent|anticaking|"
    r"anti-caking|humectant|sequestrant|flavour enhancer|flavor enhancer|"
    r"sweetener|firming|glazing|bulking|improver|conditioner)",
    re.IGNORECASE,
)


def _additive_shaped(token):
    """A token that looks like an additive: an INS/E number the parser reads, or a class word."""
    return bool(extract_ins(token) or _ADDITIVE_WORDS.search(token))


def off_enumbers(row):
    out = set()
    for tag in row.get("off_additives_tags", []):
        m = _E_TAG.match(tag)
        ins = extract_ins(m.group(1)) if m else None
        if ins:
            out.add(ins)
    return out


def engine_insnumbers(result):
    return {i for i in (extract_ins(f.get("matched_as", "")) for f in result.get("flags", [])) if i}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--csv", default=None, help="Write per-product results here.")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    rows = []
    with open(args.fixture, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    known_ins = set(engine._ADDITIVE_BY_INS.keys())

    verdicts = collections.Counter()
    nova_matrix = collections.Counter()   # (engine_bool, off_bool)
    missed_ins = collections.Counter()    # OFF found it, engine has no row
    missed_ins_products = collections.defaultdict(set)
    engine_only_ins = collections.Counter()
    unmatched_tokens = collections.Counter()
    empty_verdicts = []
    per_product = []

    for row in rows:
        text = row["ingredients_text"]
        result = engine.analyze(text)
        tokens = engine.tokenize(text)

        verdicts[result["binary"]] += 1

        # --- unmatched tokens: what the engine looked at and had nothing to say about
        for t in tokens:
            if engine.classify_token(t) is None:
                unmatched_tokens[t] += 1

        # --- additive cross-check
        off_e = off_enumbers(row)
        eng_ins = engine_insnumbers(result)
        for e in off_e - eng_ins:
            if e not in known_ins:
                missed_ins[e] += 1
                missed_ins_products[e].add(row.get("product_name") or row["code"])
        for i in eng_ins - off_e:
            engine_only_ins[i] += 1

        # --- NOVA benchmark
        off_nova = row.get("off_nova_group")
        if off_nova is not None:
            nova_matrix[(bool(result["nova_ultra_processed"]), int(off_nova) == 4)] += 1

        # --- the dangerous case: a confident CLEAN
        if result["binary"] == "clean" and not result["flags"]:
            empty_verdicts.append((row.get("product_name") or row["code"], text[:90]))

        per_product.append({
            "code": row["code"],
            "product_name": row.get("product_name"),
            "brands": row.get("brands"),
            "engine_binary": result["binary"],
            "engine_grade": result["grade"],
            "engine_score": result["score"],
            "engine_nova": result["nova_ultra_processed"],
            "off_nova_group": off_nova,
            "nova_agree": (None if off_nova is None
                           else bool(result["nova_ultra_processed"]) == (int(off_nova) == 4)),
            "flags_count": len(result["flags"]),
            "tokens_parsed": result["ingredient_count_parsed"],
            "hidden_sugar_names": "|".join(result["hidden_sugar_names"]),
            "off_additives": "|".join(sorted(off_e)),
            "engine_additives": "|".join(sorted(eng_ins)),
            "missed_by_engine": "|".join(sorted(off_e - eng_ins)),
            "needs_verification": "|".join(result["needs_verification"]),
        })

    # -----------------------------------------------------------------------
    n = len(rows)
    p = print
    p("=" * 72)
    p(f"  INSIDE LABEL — COVERAGE REPORT   ({n} products)")
    p("=" * 72)

    p("\nVERDICT DISTRIBUTION")
    for k, v in verdicts.most_common():
        p(f"  {k:<18} {v:>4}  ({v / n:.0%})")

    p("\nNOVA AGREEMENT vs Open Food Facts (independent classifier, same text)")
    tp = nova_matrix[(True, True)]
    tn = nova_matrix[(False, False)]
    fp = nova_matrix[(True, False)]
    fn = nova_matrix[(False, True)]
    scored = tp + tn + fp + fn
    if scored:
        p(f"  both say ultra-processed      {tp:>4}")
        p(f"  both say not                  {tn:>4}")
        p(f"  engine says UPF, OFF does not {fp:>4}   <- engine over-flagging, or OFF stale")
        p(f"  OFF says UPF, engine does not {fn:>4}   <- MISSED MARKERS. Look here first.")
        p(f"  agreement                     {(tp + tn) / scored:.1%}  (n={scored})")
    else:
        p("  no OFF nova_group values in this fixture")

    p(f"\nMISSED ADDITIVES — OFF detected these, your tables have no row  (top {args.top})")
    p("  Add these to additives.json in this order. Demand-driven, not guessed.")
    if not missed_ins:
        p("    none")
    for ins, count in missed_ins.most_common(args.top):
        example = sorted(missed_ins_products[ins])[0][:44]
        p(f"    INS/E {ins:<6} {count:>4} products   e.g. {example}")

    p(f"\nUNMATCHED TOKENS THAT LOOK LIKE ADDITIVES  (top {args.top})")
    p("  Not INS-numbered, but shaped like something the engine should know.")
    shaped = [(t, c) for t, c in unmatched_tokens.most_common() if _additive_shaped(t)]
    if not shaped:
        p("    none")
    for t, c in shaped[:args.top]:
        p(f"    {c:>4}x  {t[:60]}")

    p(f"\nUNMATCHED TOKENS, EVERYTHING ELSE  (top {args.top})")
    p("  Mostly plain foods the engine is right to ignore. Scan for synonyms")
    p("  and Indian spellings worth adding to normalization.json.")
    others = [(t, c) for t, c in unmatched_tokens.most_common() if not _additive_shaped(t)]
    for t, c in others[:args.top]:
        p(f"    {c:>4}x  {t[:60]}")

    p(f"\nCLEAN VERDICTS WITH ZERO FLAGS  ({len(empty_verdicts)})")
    p("  Each is either a genuinely simple product or a total parse failure.")
    p("  These two look identical to a user. Read every one by hand.")
    for name, snippet in empty_verdicts[:args.top]:
        p(f"    {str(name)[:34]:<34} | {snippet}")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(per_product[0].keys()))
            w.writeheader()
            w.writerows(per_product)
        p(f"\nper-product CSV -> {args.csv}")

    p("\n" + "=" * 72)
    p("  Disagreement is a lead, not a verdict. OFF is crowdsourced and its")
    p("  additive detection has its own misses — a row where OFF found nothing")
    p("  and your engine flagged INS 621 is very possibly your engine being")
    p("  right. Read the text before changing a table.")
    p("=" * 72)


if __name__ == "__main__":
    main()

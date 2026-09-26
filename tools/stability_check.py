#!/usr/bin/env python3
"""
Run the same images through the vision layer N times and measure how much the
answer moves.

    python3 tools/stability_check.py --id limca-pet-1l \
        --back photos/limca-back.png --front photos/limca-front.png -n 5

WHY THIS EXISTS
    Temperature 0 is not a determinism guarantee. On the Limca label the model
    returned six ingredients on one run and five on the next, dropping
    PRESERVATIVE (211) -- a moderate-concern additive that is plainly printed
    on the pack. Same image, same prompt, same config, 12 points of score
    difference.

    That has two consequences worth being blunt about:

    1. A single run per label makes eval_vision meaningless. Your accuracy
       number becomes a function of which run you happened to save. Gold built
       against one lucky run sets the ceiling in the wrong place.

    2. Two users scanning the same product can get different verdicts. That is
       a product problem before it is an engineering one, and no amount of
       prompt tuning removes it entirely -- it can only be measured, reduced,
       and designed around.

WHAT TO DO WITH THE OUTPUT
    Unstable entries are the actionable part: an ingredient present in some
    runs and absent in others is exactly what prompt work should target. Score
    range tells you how wrong a single-run verdict can be.
"""

import argparse
import collections
import json
import mimetypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.core import engine  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402


def load(path, role):
    if not path:
        return None
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return (f.read(), mime, role)


def summarise(runs, quiet=False):
    """runs: list of vision dicts. Returns the report dict; prints it too."""
    n = len(runs)
    p = (lambda *a: None) if quiet else print

    entry_counts = collections.Counter()
    ins_counts = collections.Counter()
    scores, grades, binaries, flagsets = [], [], [], []
    signatures = collections.Counter()

    for v in runs:
        ings = v.get("ingredients", [])
        norm = tuple(sorted(x.strip().rstrip(".").upper() for x in ings))
        signatures[norm] += 1
        for x in norm:
            entry_counts[x] += 1

        raw = ", ".join(ings)
        for i in _ins_of(ings):
            ins_counts[i] += 1

        r = engine.analyze(raw) if ings else None
        if r:
            scores.append(r["score"])
            grades.append(r["grade"])
            binaries.append(r["binary"])
            flagsets.append(tuple(sorted(f["matched_as"] for f in r["flags"])))

    p("=" * 68)
    p(f"  STABILITY   {n} runs of the same images")
    p("=" * 68)

    p(f"\nDISTINCT INGREDIENT SETS        {len(signatures)}")
    for sig, c in signatures.most_common():
        p(f"  {c}/{n} runs -> {len(sig)} entries")

    unstable = {k: c for k, c in entry_counts.items() if c < n}
    p(f"\nUNSTABLE ENTRIES                {len(unstable)}")
    p("  Present in some runs, absent in others. Target prompt work here.")
    if not unstable:
        p("    none - every run returned the same entries")
    for k, c in sorted(unstable.items(), key=lambda x: x[1]):
        p(f"    {c}/{n} runs   {k[:64]}")

    unstable_ins = {k: c for k, c in ins_counts.items() if c < n}
    p(f"\nUNSTABLE INS NUMBERS            {len(unstable_ins)}")
    p("  These move the score directly.")
    if not unstable_ins:
        p("    none")
    for k, c in sorted(unstable_ins.items(), key=lambda x: x[1]):
        p(f"    {c}/{n} runs   INS {k}")

    if scores:
        lo, hi = min(scores), max(scores)
        p(f"\nSCORE                           {lo}-{hi}   spread {hi - lo}")
        p(f"GRADE                           {sorted(set(grades))}")
        p(f"BINARY                          {sorted(set(binaries))}")
        p(f"DISTINCT FLAG SETS              {len(set(flagsets))}")
        if hi - lo >= 10:
            p("\n  A single run can be wrong by more than a full grade band.")
            p("  Do not build a gold set from one run per label.")

    p("=" * 68)
    return {
        "runs": n,
        "distinct_ingredient_sets": len(signatures),
        "unstable_entries": unstable,
        "unstable_ins": unstable_ins,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "grades": sorted(set(grades)),
        "distinct_flag_sets": len(set(flagsets)),
    }


def _ins_of(ingredients):
    from insidelabel.core.tokenize import ins_numbers   # the one INS parser (D-099)
    return ins_numbers(ingredients)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--back", required=True)
    ap.add_argument("--front", default=None)
    ap.add_argument("-n", "--runs", type=int, default=5)
    ap.add_argument("--out", default="runs", help="Directory for every individual run.")
    ap.add_argument("--report", default=None, help="Write the summary JSON here.")
    args = ap.parse_args()

    images = [i for i in (load(args.back, "back"), load(args.front, "front")) if i]
    os.makedirs(args.out, exist_ok=True)

    runs = []
    for k in range(1, args.runs + 1):
        print(f"  run {k}/{args.runs} ...", file=sys.stderr, flush=True)
        try:
            vision, _ = gemini.analyze_images(images)
        except gemini.VisionError as e:
            print(f"  run {k} failed: {e}", file=sys.stderr)
            continue
        runs.append(vision)
        with open(os.path.join(args.out, f"{args.id}.run{k}.json"), "w", encoding="utf-8") as f:
            json.dump(vision, f, ensure_ascii=False, indent=2)

    if not runs:
        print("no successful runs", file=sys.stderr)
        sys.exit(2)

    print()
    report = summarise(runs)
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)


if __name__ == "__main__":
    main()

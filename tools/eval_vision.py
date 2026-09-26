#!/usr/bin/env python3
"""
Score vision output against hand-checked ground truth.

    python3 tools/eval_vision.py --gold gold/ --pred predictions/ --csv reports/vision_eval.csv

THE METRIC THAT MATTERS
    Character accuracy is the wrong number. If the model reads "Rolled Oats" as
    "Rolled Qats" the verdict is identical and nobody is harmed. If it drops a
    single "INS 621" the verdict changes and a user is misled.

    So the headline number here is VERDICT-CHANGING ERROR RATE: run engine.py
    on the gold ingredients, run it on the predicted ingredients, and count how
    often the two disagree. That is the only accuracy figure that maps onto
    what a person actually sees.

    Everything else - ingredient F1, INS recall - exists to tell you WHY a
    verdict flipped, once you know that it did.

FILE LAYOUT
    gold/<id>.json  and  predictions/<id>.json, matched on filename stem.
    Both files use the schema in app/vision/prompt.py, so a gold file is just a
    prediction you have corrected by hand.

BUILDING THE GOLD SET
    This is the expensive part and there is no way around it. Transcribe the
    label yourself from the photo, in the schema, and be strict: gold that was
    lightly edited from the model's own output will agree with the model and
    tell you nothing.
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
from insidelabel.core.tokenize import ins_numbers  # noqa: E402  (the one INS parser, D-099)

# Extract INS numbers using the ENGINE's own parsing, not a parallel regex.
# The first version of this file used a prefix-only pattern, which found zero
# INS numbers on a bare-number label like Limca -- so it compared two empty
# sets and reported a vacuous F1 of 1.000 while an additive had been dropped.
# A harness that reimplements the parser it is grading will drift from it and
# score its own blind spots as perfect.


def norm(s):
    """Loose normalisation for set comparison - punctuation and case are noise."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9%() ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ins_set(ingredients):
    """
    INS numbers as the engine would see them, bare-number labels included. The
    engine's own parser (D-099): the old private pattern read 3 digits only, so
    1422 counted as 142 on both sides and "160 a(ii)" as 160.
    """
    return ins_numbers(ingredients)


def prf(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    r = tp / len(gold) if gold else 1.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def load_dir(path):
    out = {}
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                out[os.path.splitext(fn)[0]] = json.load(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    gold = load_dir(args.gold)
    pred = load_dir(args.pred)
    ids = sorted(set(gold) & set(pred))
    missing = sorted(set(gold) - set(pred))

    if not ids:
        print("No matching id pairs between gold and pred.", file=sys.stderr)
        sys.exit(1)

    # A predictions directory containing more than one model is not one
    # experiment, it is two averaged together. Say so rather than reporting a
    # single number across both.
    # Scoped to the labels actually scored. Computing this over every file in
    # predictions/ raised a false alarm from stale leftovers that have no gold
    # counterpart and were never part of the run.
    models = {pred[i].get("_model", "unrecorded") for i in ids}
    if len(models) > 1:
        print(f"\n  !! predictions were produced by MORE THAN ONE MODEL: "
              f"{sorted(models)}")
        print("  !! These numbers are not comparable. Re-run all labels on one")
        print("  !! model before reading anything below.\n")

    rows = []
    flips = []
    ins_missed = collections.Counter()
    ins_hallucinated = collections.Counter()
    status_wrong = collections.Counter()
    identity_wrong = collections.Counter()
    identity_checked = collections.Counter()

    agg = collections.Counter()
    f_ing = f_ins = f_claim = 0.0

    for i in ids:
        g, p = gold[i], pred[i]

        g_ing = {norm(x) for x in g.get("ingredients", [])}
        p_ing = {norm(x) for x in p.get("ingredients", [])}
        _, _, fi = prf(p_ing, g_ing)

        g_ins, p_ins = ins_set(g.get("ingredients", [])), ins_set(p.get("ingredients", []))
        ip, ir, fn_ = prf(p_ins, g_ins)
        for x in g_ins - p_ins:
            ins_missed[x] += 1
        for x in p_ins - g_ins:
            ins_hallucinated[x] += 1

        g_cl = {norm(x) for x in g.get("front_claims", [])}
        p_cl = {norm(x) for x in p.get("front_claims", [])}
        _, _, fc = prf(p_cl, g_cl)

        # Product identity. Added after a real miss: the model correctly left
        # net_quantity null on a pack that never prints it, while the
        # hand-written gold had derived 2000ml from "200ml x 10 servings".
        # The eval scored that run 1.000 across the board because it was not
        # looking at this object at all. A gold error the harness cannot see is
        # worse than a model error it can.
        gp, pp = g.get("product") or {}, p.get("product") or {}
        for k in ("brand", "name", "variant", "net_quantity", "veg_mark"):
            gv_, pv_ = gp.get(k), pp.get(k)
            identity_checked[k] += 1
            gn = norm(gv_) if isinstance(gv_, str) else gv_
            pn = norm(pv_) if isinstance(pv_, str) else pv_
            if gn != pn:
                identity_wrong[f"{k}: gold={gv_!r} pred={pv_!r}"] += 1
                agg[f"identity_{k}_wrong"] += 1

        for k in ("front_status", "back_status", "ingredients_status"):
            if g.get(k) != p.get(k):
                status_wrong[f"{k}: gold={g.get(k)} pred={p.get(k)}"] += 1

        # --- the headline: does the verdict survive the transcription?
        gv = engine.analyze(", ".join(g.get("ingredients", []) or ["__none__"]))
        pv = engine.analyze(", ".join(p.get("ingredients", []) or ["__none__"]))
        same_binary = gv["binary"] == pv["binary"]
        same_nova = gv["nova_ultra_processed"] == pv["nova_ultra_processed"]
        agg["binary_match"] += same_binary
        agg["nova_match"] += same_nova
        delta = abs(pv["score"] - gv["score"])
        agg["score_drift_total"] += delta
        if delta >= 10:
            agg["score_drift_material"] += 1
        if sorted(f["matched_as"] for f in gv["flags"]) != sorted(f["matched_as"] for f in pv["flags"]):
            agg["flagset_differs"] += 1
        if not same_binary:
            flips.append((i, gv["binary"], pv["binary"], sorted(g_ins - p_ins), sorted(p_ins - g_ins)))

        f_ing += fi
        f_ins += fn_
        f_claim += fc

        rows.append({
            "id": i,
            "gold_binary": gv["binary"], "pred_binary": pv["binary"],
            "binary_match": same_binary,
            "gold_score": gv["score"], "pred_score": pv["score"],
            "score_delta": pv["score"] - gv["score"],
            "ingredient_f1": round(fi, 3),
            "ins_f1": round(fn_, 3), "ins_precision": round(ip, 3), "ins_recall": round(ir, 3),
            "claim_f1": round(fc, 3),
            "ins_missed": "|".join(sorted(g_ins - p_ins)),
            "ins_hallucinated": "|".join(sorted(p_ins - g_ins)),
        })

    n = len(ids)
    p_ = print
    p_("=" * 72)
    p_(f"  VISION EVAL   ({n} labels)   model: {', '.join(sorted(models))}")
    p_("=" * 72)
    p_(f"\nVERDICT-CHANGING ERROR RATE      {1 - agg['binary_match'] / n:.1%}")
    p_(f"  verdict preserved              {agg['binary_match']}/{n}  ({agg['binary_match']/n:.1%})")
    p_(f"  NOVA call preserved            {agg['nova_match']}/{n}  ({agg['nova_match']/n:.1%})")
    p_(f"\nFLAG SET CHANGED                 {agg['flagset_differs']}/{n}  ({agg['flagset_differs']/n:.1%})")
    p_(f"MEAN ABSOLUTE SCORE DRIFT        {agg['score_drift_total']/n:.1f} points")
    p_(f"SCORE DRIFT >= 10 POINTS         {agg['score_drift_material']}/{n}")
    p_("  Binary is coarse - most Indian packaged food is ultra-processed on")
    p_("  several markers at once, so one dropped additive rarely flips it.")
    p_("  Flag-set change and score drift catch the errors binary hides. A")
    p_("  0% verdict-changing rate with a high flag-set change rate means the")
    p_("  receipts you show the user are wrong even though the headline is right.")

    p_(f"\nINS NUMBER F1                    {f_ins / n:.3f}")
    p_(f"INGREDIENT SET F1                {f_ing / n:.3f}")
    p_(f"FRONT CLAIM F1                   {f_claim / n:.3f}")

    p_(f"\nVERDICT FLIPS  ({len(flips)})")
    if not flips:
        p_("  none")
    for i, gb, pb, missed, hall in flips:
        p_(f"  {i:<22} gold={gb:<16} pred={pb}")
        if missed:
            p_(f"      dropped INS: {', '.join(missed)}")
        if hall:
            p_(f"      invented INS: {', '.join(hall)}")

    p_(f"\nMOST-DROPPED INS NUMBERS")
    for k, v in ins_missed.most_common(12):
        p_(f"  {k:<8} missed on {v} labels")
    if not ins_missed:
        p_("  none")

    p_(f"\nHALLUCINATED INS NUMBERS  (invented, not on the label)")
    p_("  Any entry here is worse than a miss - it is a fact with no source.")
    for k, v in ins_hallucinated.most_common(12):
        p_(f"  {k:<8} invented on {v} labels")
    if not ins_hallucinated:
        p_("  none")

    p_(f"\nPRODUCT IDENTITY")
    id_fields = ("brand", "name", "variant", "net_quantity", "veg_mark")
    for k in id_fields:
        wrong = agg[f"identity_{k}_wrong"]
        p_(f"  {k:<14} {n - wrong}/{n} match")
    if identity_wrong:
        p_("  mismatches:")
        for k, v in identity_wrong.most_common(10):
            p_(f"    {v:>3}x  {k}")
    p_("  A mismatch here is as likely to be a gold error as a model error -")
    p_("  read the pack before assuming the model was wrong.")

    p_(f"\nSTATUS FIELD ERRORS")
    for k, v in status_wrong.most_common():
        p_(f"  {v:>3}x  {k}")
    if not status_wrong:
        p_("  none")

    if missing:
        p_(f"\nGOLD WITH NO PREDICTION  ({len(missing)}): {', '.join(missing[:10])}")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        p_(f"\nper-label CSV -> {args.csv}")
    p_("=" * 72)


if __name__ == "__main__":
    main()

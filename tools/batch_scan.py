#!/usr/bin/env python3
"""
Scan a whole directory of label photos.

    photos/
      britannia-nutrichoice-back.jpg
      britannia-nutrichoice-front.jpg
      haldiram-bhujia-back.jpg
      ...

    python3 tools/batch_scan.py --photos photos/ --out predictions/
    python3 tools/eval_vision.py --gold gold/ --pred predictions/

Files pair on the stem before -back / -front. A back image is required; a
front is optional.

DESIGN NOTE
    Skips ids that already have a prediction unless --force. Vision calls cost
    money and time, and re-running thirty labels to add one is the kind of
    friction that stops people adding the one.
"""

import argparse
import glob
import json
import mimetypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.core import engine  # noqa: E402
from insidelabel.reliability import gates as rel  # noqa: E402
from insidelabel.extraction.providers import gemini, ocr_check  # noqa: E402

RATE_IN, RATE_OUT = 0.75, 3.75   # USD per 1M tokens; see scan_label.py note

EXTS = ("jpg", "jpeg", "png", "webp", "heic")


def discover(photos_dir):
    """Return {id: {"back": path, "front": path|None}}."""
    found = {}
    for ext in EXTS:
        for path in glob.glob(os.path.join(photos_dir, f"*.{ext}")) + \
                    glob.glob(os.path.join(photos_dir, f"*.{ext.upper()}")):
            stem = os.path.splitext(os.path.basename(path))[0]
            for role in ("back", "front"):
                for sep in ("-", "_"):
                    if stem.lower().endswith(f"{sep}{role}"):
                        pid = stem[: -(len(role) + 1)]
                        found.setdefault(pid, {"back": None, "front": None})
                        found[pid][role] = path
    return {k: v for k, v in sorted(found.items())}


def load(path, role):
    if not path:
        return None
    with open(path, "rb") as f:
        return (f.read(), mimetypes.guess_type(path)[0] or "image/jpeg", role)


def scan_one(paths, note=None):
    images = [i for i in (load(paths["back"], "back"), load(paths["front"], "front")) if i]
    vision, corrections = gemini.analyze_images(images, on_attempt=note)

    back_bytes = next((d for d, _m, r in images if r == "back"), None)
    front_bytes = next((d for d, _m, r in images if r == "front"), None)

    ocr_res = {"available": False, "reason": "no back image"}
    if back_bytes and vision.get("ingredients"):
        fixed, ocr_res, recovered = ocr_check.recover_entries(back_bytes, vision["ingredients"])
        if recovered:
            vision["ingredients"] = fixed
            corrections.append(f"OCR recovered omitted additive(s): {ocr_res['missing']}")
    vision["_ocr_cross_check"] = ocr_res

    dg, idrep = ocr_check.check_identity_anchors(vision, front_bytes, back_bytes)
    vision["_identity_corroboration"] = idrep
    if dg and (vision.get("product_match") or {}).get("status") == "match":
        vision["product_match"]["status"] = "indeterminate"
        corrections.append("product_match downgraded: back brand not corroborated by OCR")

    proceed, reliability = rel.assess(vision)
    verdict = engine.analyze(", ".join(vision["ingredients"])) if proceed else None
    return vision, corrections, reliability, verdict, proceed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", default="photos")
    ap.add_argument("--out", default="predictions")
    ap.add_argument("--force", action="store_true", help="Re-scan ids that already have a prediction.")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    pairs = discover(args.photos)
    if not pairs:
        print(f"No <id>-back.<ext> files in {args.photos}/", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    done = skipped = failed = 0
    summary = []

    for pid, paths in pairs.items():
        target = os.path.join(args.out, f"{pid}.json")
        if os.path.exists(target) and not args.force:
            skipped += 1
            continue
        if not paths["back"]:
            print(f"  {pid}: no back image, skipped", file=sys.stderr)
            failed += 1
            continue

        print(f"  {pid} ...", end="", file=sys.stderr, flush=True)
        t0 = time.time()

        def _note(attempt, delay, err):
            print(f"\n    upstream busy (attempt {attempt}), retrying in {delay:.1f}s",
                  file=sys.stderr, flush=True)

        try:
            vision, corr, reliability, verdict, ok = scan_one(paths, _note)
            print(f" {time.time() - t0:.1f}s", file=sys.stderr, flush=True)
        except Exception as e:                                    # noqa: BLE001
            print(f" FAILED after {time.time() - t0:.1f}s\n    {type(e).__name__}: {e}",
                  file=sys.stderr)
            failed += 1
            continue

        with open(target, "w", encoding="utf-8") as f:
            json.dump(vision, f, ensure_ascii=False, indent=2)
        done += 1
        u = dict(gemini.LAST_USAGE)
        summary.append({
            "tokens": u.get("total_tokens"),
            "cost": ((u.get("input_tokens") or 0) * RATE_IN
                     + (u.get("output_tokens") or 0) * RATE_OUT) / 1_000_000,
            "id": pid,
            "gold_exists": os.path.exists(os.path.join("gold", f"{pid}.json")),
            "verdict": verdict["binary"] if verdict else None,
            "grade": verdict["grade"] if verdict else None,
            "score": verdict["score"] if verdict else None,
            "flags": len(verdict["flags"]) if verdict else 0,
            "corrections": len(corr),
            "front_claims": len(vision.get("front_claims") or []),
            "pairing": (vision.get("product_match") or {}).get("status"),
        })
        time.sleep(args.sleep)

    total_cost = sum(s.get("cost") or 0 for s in summary)
    total_tok = sum(s.get("tokens") or 0 for s in summary)
    print(f"\nscanned {done}, skipped {skipped} (already present), failed {failed}")
    if total_tok:
        print(f"tokens {total_tok:,}  ~${total_cost:.4f} this batch  "
              f"(~${(total_cost/max(done,1))*1000:.2f} per 1,000 scans)\n")
    else:
        print()
    if summary:
        hdr = f"{'id':<32}{'gold':<6}{'verdict':<18}{'gr':<4}{'score':<7}{'flags':<7}{'fixes':<7}{'claims':<8}pairing"
        print(hdr); print("-" * len(hdr))
        for s in summary:
            print(f"{s['id'][:31]:<32}{'yes' if s['gold_exists'] else 'NO':<6}"
                  f"{str(s['verdict']):<18}{str(s['grade']):<4}{str(s['score']):<7}"
                  f"{s['flags']:<7}{s['corrections']:<7}{s['front_claims']:<8}{s['pairing']}")

    missing_gold = [s["id"] for s in summary if not s["gold_exists"]]
    if missing_gold:
        print(f"\n{len(missing_gold)} label(s) have no gold file, so nothing about them")
        print("is measured. Write gold BEFORE reading their predictions:")
        for m in missing_gold:
            print(f"    python3 tools/new_gold.py --id {m}")


if __name__ == "__main__":
    main()

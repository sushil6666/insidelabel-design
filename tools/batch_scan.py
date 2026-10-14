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

D-193: the read's settings, for the advisor's gold-set run (each one a switch on the
server, all off there until this run shows a setting faster with no loss in reading):

    python3 tools/batch_scan.py --photos photos/ --out <scratch>/pred-minimal --thinking-level minimal
    python3 tools/batch_scan.py --photos photos/ --out <scratch>/pred-split --split-front
    python3 tools/batch_scan.py --photos photos/ --out <scratch>/pred-low-media --media-resolution low

Each prints seconds per read and tokens, and each prediction keeps its settings
(_read_settings) and tokens (_usage). Predictions go to a scratch folder: --out
inside reports/ is refused (CLAUDE.md).

D-192: --reader claude reads with Claude (claude-haiku-5-5, or INSIDELABEL_CLAUDE_MODEL)
instead of Gemini, for the advisor's gold-set comparison; it needs ANTHROPIC_API_KEY:

    python3 tools/batch_scan.py --photos photos/ --out <scratch>/pred-claude --reader claude
    python3 tools/eval_vision.py --gold gold/ --pred <scratch>/pred-claude

Unset, the environment's INSIDELABEL_READER decides (gemini unless it says claude). The
three D-193 switches are Gemini's, so they are refused with --reader claude.

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

# USD per 1M tokens (input, output), by the reader that answered (D-192). Gemini 3.6 Flash
# until 31 Dec 2026 (see scan_label.py note); claude-haiku-5-5 for prompts up to 100,000 tokens.
RATES = {"gemini": (0.75, 3.75), "claude": (0.10, 0.50)}

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
    settings = gemini.read_settings()
    t0 = time.monotonic()
    if settings["split_front"] and paths["front"]:
        # D-193: as /scan does it: the front's call beside the back's, joined only when it is
        # in by the time the back's answer is (the result never waits for the front).
        front = gemini.FrontRead([i for i in images if i[2] == "front"])
        vision, corrections = gemini.analyze_split(images, front, on_attempt=note)
        back_s = time.monotonic() - t0
        front.done.wait()
        vision["_front"] = {"joined": vision.pop("_front_joined", False), "error": front.error,
                            "seconds": round(time.monotonic() - t0, 2), "usage": dict(front.usage) or None}
    else:
        vision, corrections = gemini.analyze_images(images, on_attempt=note)
        back_s = time.monotonic() - t0
    vision["_read_settings"] = settings
    vision["_seconds"] = round(back_s, 2)

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


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", default="photos")
    ap.add_argument("--out", default="predictions")
    ap.add_argument("--force", action="store_true", help="Re-scan ids that already have a prediction.")
    ap.add_argument("--sleep", type=float, default=1.0)
    # D-193: the read's settings for this run (the same switches the server reads).
    ap.add_argument("--split-front", action="store_true", help="Read the back and the front in two calls at once.")
    ap.add_argument("--thinking-level", choices=gemini.THINKING_LEVELS, help="Default: low, as the server.")
    ap.add_argument("--media-resolution", choices=gemini.MEDIA_RESOLUTIONS, help="Default: the API's own.")
    # D-192: which model reads. Unset: the environment's INSIDELABEL_READER (gemini by default).
    ap.add_argument("--reader", choices=gemini.READERS, help="Default: INSIDELABEL_READER, else gemini.")
    args = ap.parse_args(argv)
    if args.reader == "claude" and (args.split_front or args.thinking_level or args.media_resolution):
        ap.error("--split-front, --thinking-level and --media-resolution are Gemini's; they do nothing "
                 "with --reader claude")
    return args


def apply_args(args):
    """The run's settings, as the switches the server reads."""
    for flag, env, value in ((args.split_front, "INSIDELABEL_READ_SPLIT_FRONT", "on"),
                             (args.thinking_level, "INSIDELABEL_THINKING_LEVEL", args.thinking_level),
                             (args.media_resolution, "INSIDELABEL_MEDIA_RESOLUTION", args.media_resolution),
                             (args.reader, "INSIDELABEL_READER", args.reader)):
        if flag:
            os.environ[env] = value


def main():
    args = parse_args()
    if os.path.realpath(args.out).startswith(os.path.realpath(os.path.join(ROOT, "reports")) + os.sep) or \
            os.path.realpath(args.out) == os.path.realpath(os.path.join(ROOT, "reports")):
        sys.exit("--out is inside reports/: write predictions to a scratch folder (CLAUDE.md).")
    apply_args(args)
    print(f"read settings: {gemini.read_settings()}", file=sys.stderr)

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
            u = vision.get("_usage") or {}
            read = vision.get("_read") or {}
            print(f" {time.time() - t0:.1f}s, {read.get('reader', '?')}"
                  + (f" ({read['fallback_why']}: Gemini read it)" if read.get("fallback") else "")
                  + f", tokens in {u.get('input_tokens')} out {u.get('output_tokens')}",
                  file=sys.stderr, flush=True)
        except Exception as e:                                    # noqa: BLE001
            print(f" FAILED after {time.time() - t0:.1f}s\n    {type(e).__name__}: {e}",
                  file=sys.stderr)
            failed += 1
            continue

        with open(target, "w", encoding="utf-8") as f:
            json.dump(vision, f, ensure_ascii=False, indent=2)
        done += 1
        u = vision.get("_usage") or {}                         # D-193: this read's own tokens
        rate_in, rate_out = RATES.get((vision.get("_read") or {}).get("reader"), RATES["gemini"])
        summary.append({
            "seconds": vision.get("_seconds"),
            "input": u.get("input_tokens"), "output": u.get("output_tokens"), "thinking": u.get("thinking_tokens"),
            "tokens": u.get("total_tokens"),
            "cost": ((u.get("input_tokens") or 0) * rate_in
                     + (u.get("output_tokens") or 0) * rate_out) / 1_000_000,
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
    secs = sorted(s["seconds"] for s in summary if s.get("seconds") is not None)
    if secs:
        print(f"seconds per read: median {secs[len(secs) // 2]:.1f}, slowest {secs[-1]:.1f} "
              f"(the result's wait; with --split-front, the back's call only)")
        for key in ("input", "output", "thinking"):
            vals = [s[key] for s in summary if s.get(key) is not None]
            if vals:
                print(f"  {key} tokens: total {sum(vals):,}, mean {sum(vals) / len(vals):,.0f}")
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

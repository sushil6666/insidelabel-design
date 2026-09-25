#!/usr/bin/env python3
"""
Compare the independent OCR readers on the gold labels (D-093).

For each gold label with a back photo, and for each reader (Tesseract, Cloud
Vision), measures:

  time       seconds for the cross-check on that photo
  recall     INS numbers printed on the label (gold transcription) that the
             reader found; this is what lets it catch a model omission
  invented   INS numbers it found that are NOT on the label (known table rows
             only; these are the ones recovery could inject)
  would add  what recover_entries would add to the recorded model read, and
             whether each addition is really on the label; a wrong addition is
             the one failure that must stay at zero

    GOOGLE_VISION_KEY=… python tools/compare_ocr.py --csv /tmp/ocr.csv
    python tools/compare_ocr.py --readers tesseract          # baseline only

Writes nothing under reports/ unless --csv points there.
"""
import argparse
import csv
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.core import engine  # noqa: E402
from insidelabel.extraction.providers import cloud_vision, ocr_check  # noqa: E402


def gold_ins(name):
    with open(os.path.join(ROOT, "gold", f"{name}.json"), encoding="utf-8") as f:
        raw = ", ".join(json.load(f)["ingredients"])
    return {i for i in ocr_check._ins_numbers(raw) if i in engine._ADDITIVE_BY_INS}


def model_read(name):
    p = os.path.join(ROOT, "predictions", f"{name}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("ingredients")


def run(reader, photo, model):
    os.environ["INSIDELABEL_OCR"] = reader
    cloud_vision._CACHE.clear()                 # time a real read, not the cache
    t0 = time.monotonic()
    r = ocr_check.cross_check(photo, [])        # everything it finds counts as "missing"
    secs = time.monotonic() - t0
    adds = ocr_check.cross_check(photo, model)["missing"] if (model and r.get("available")) else []
    return r, secs, adds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--readers", default="tesseract,cloud_vision")
    ap.add_argument("--csv")
    a = ap.parse_args()
    readers = a.readers.split(",")
    if "cloud_vision" in readers and not cloud_vision.configured():
        sys.exit("cloud_vision needs GOOGLE_VISION_KEY (or pass --readers tesseract)")

    rows = []
    for g in sorted(glob.glob(os.path.join(ROOT, "gold", "*.json"))):
        name = os.path.basename(g)[:-5]
        photos = glob.glob(os.path.join(ROOT, "photos", f"{name}-back.*"))
        if not photos:
            print(f"{name}: no back photo, skipped")
            continue
        photo = open(photos[0], "rb").read()
        gold, model = gold_ins(name), model_read(name)
        for reader in readers:
            r, secs, adds = run(reader, photo, model)
            found = set(r.get("ocr_ins") or [])
            ran = r.get("reader") or "none"
            row = {
                "label": name, "reader": reader, "ran": ran, "seconds": round(secs, 1),
                "gold_ins": len(gold), "found": len(found & gold),
                "recall": round(len(found & gold) / len(gold), 2) if gold else None,
                "invented": " ".join(sorted(found - gold)),
                "would_add": " ".join(adds),
                "wrong_adds": " ".join(sorted(set(adds) - gold)),
            }
            rows.append(row)
            flag = "  <-- WRONG ADDITION" if row["wrong_adds"] else ""
            fell = f" (fell back: {r.get('fallback_from')})" if ran != reader else ""
            print(f"{name:34} {reader:12} {row['seconds']:6.1f}s  found {row['found']}/{row['gold_ins']}"
                  f"  invented [{row['invented']}]  would add [{row['would_add']}]{flag}{fell}")

    print()
    for reader in readers:
        rs = [r for r in rows if r["reader"] == reader]
        if not rs:
            continue
        tot_gold = sum(r["gold_ins"] for r in rs)
        tot_found = sum(r["found"] for r in rs)
        wrong = sum(bool(r["wrong_adds"]) for r in rs)
        fell = sum(r["ran"] != reader for r in rs)
        print(f"{reader:12}  total {sum(r['seconds'] for r in rs):6.1f}s  "
              f"mean {sum(r['seconds'] for r in rs) / len(rs):5.1f}s/label  "
              f"recall {tot_found}/{tot_gold}  labels with a wrong addition: {wrong}"
              + (f"  fell back on {fell}" if fell else ""))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()

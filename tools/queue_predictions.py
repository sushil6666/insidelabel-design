#!/usr/bin/env python3
"""
Send recorded scans (photos/<id>-back|front.* + predictions/<id>.json) through
/scan with the database on, so they land in the review queue — no vision call,
no cost. The recorded model output is replayed; the real photos are stored for
the reviewer to check against.

    INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \\
        python tools/queue_predictions.py [--ids limca-pet-1l ...]

Safe to re-run: an identical version already waiting for review is reused.
"""
import argparse
import glob
import mimetypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", help="prediction ids (default: all in predictions/)")
    ap.add_argument("--pred", default=os.path.join(ROOT, "predictions"))
    ap.add_argument("--photos", default=os.path.join(ROOT, "photos"))
    args = ap.parse_args()
    if not os.environ.get("INSIDELABEL_DB"):
        sys.exit("Set INSIDELABEL_DB to the Postgres URI to queue into.")

    from fastapi.testclient import TestClient
    from insidelabel.api import main as api

    client = TestClient(api.app)
    ids = args.ids or sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(args.pred, "*.json")))
    for pid in ids:
        with open(os.path.join(args.pred, f"{pid}.json"), encoding="utf-8") as f:
            replay = f.read()
        files = {}
        for role in ("back", "front"):
            hits = glob.glob(os.path.join(args.photos, f"{pid}-{role}.*"))
            if hits:
                mime = mimetypes.guess_type(hits[0])[0] or "image/jpeg"
                with open(hits[0], "rb") as img:
                    files[role] = (os.path.basename(hits[0]), img.read(), mime)
        if "back" not in files:
            print(f"  skip {pid}: no back photo")
            continue
        # The recorded front was read from the same pack, so the pairing is attested.
        r = client.post("/scan", files=files, data={"replay": replay, "pairing_confirmed": "true"})
        j = r.json()
        cat = j.get("catalogue") or {}
        print(f"  {pid:34} HTTP {r.status_code}  version={cat.get('product_version_id')}  "
              f"queued={cat.get('queued_for_review')}  status={cat.get('status')}")


if __name__ == "__main__":
    main()

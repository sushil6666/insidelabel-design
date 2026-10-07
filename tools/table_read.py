#!/usr/bin/env python3
"""
D-174: read the nutrition table of a pack sent to us from the photos we hold, and show
what nutrition.check() kept. Stored in review_table_reads like the automatic read (D-092);
it never changes the catalogue: only a reviewer's tick on /review publishes a table.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"
    python tools/table_read.py 71                   # an earlier answer if one copied it, else one paid read
    python tools/table_read.py 71 --free            # the stored answers only, no model call
    python tools/table_read.py 71 --replay a.json   # a recorded table answer, no model call
    python tools/table_read.py 71 --show            # the reads stored for the item

On the server: `il tools/table_read.py ...` (DEPLOY.md). A paid read needs GEMINI_API_KEY
(about Rs 0.6), and Cloud Vision's key when the scan stored no text of its photo (13 paise).
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import table_read  # noqa: E402
from insidelabel.review.service import ReviewService  # noqa: E402


def _show(row):
    print(f"read {row['id']}  item {row['review_item_id']}  {row['created_at']:%Y-%m-%d %H:%M}  {row['source']}"
          f"  prompt {row['prompt_version']}  scan {row['scan_id']}")
    if row["model_error"]:
        print(f"  error: {row['model_error']}")
    panel = row["panel"] or {}
    print(f"  status: {panel.get('status') or 'nothing read'}  second reading: {row['ocr_reader'] or 'none'}")
    for k, v in (panel.get("values") or {}).items():
        print(f"    {k:16} {v['printed']}")
    for d in panel.get("dropped") or []:
        print(f"  not shown: {d['key']} ({d['reason']})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", type=int)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    ap.add_argument("--free", action="store_true", help="stored answers only, no model call")
    ap.add_argument("--replay", help="a recorded table answer (JSON file) instead of a call")
    ap.add_argument("--show", action="store_true", help="list the stored reads, read nothing")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    service = ReviewService(a.db, None)            # never publishes
    if a.show:
        for row in service.table_reads(a.item):
            _show(row)
        return 0
    call = None
    if a.replay:
        text = open(a.replay, encoding="utf-8").read()
        call = lambda _prompt, _images: text      # noqa: E731
    row = table_read.read_for_item(service, LocalMedia(a.media), a.item, paid=not a.free, call=call,
                                   requested_by="tools/table_read.py")
    if row is None:
        print("Nothing to read: not a send_to_us item, no photo, or (with --free) no stored answer with a table.")
        return 1
    _show(row)
    if row["source"] == "table_read" and not a.replay and gemini.LAST_USAGE:
        print(f"  tokens: {gemini.LAST_USAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

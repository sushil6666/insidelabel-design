#!/usr/bin/env python3
"""
"Send feedback" from the app (D-102): what people wrote, newest first.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"

    python tools/feedback.py                  # newest 100
    python tools/feedback.py --limit 20

D-184: no invite codes any more, so there is nothing to make, reset or revoke.
Feedback sent before D-162 still shows the code it came with.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.db.store import Store  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--limit", type=int, default=100)
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    rows = Store(a.db).feedback_list(a.limit)
    if not rows:
        print("no feedback yet")
    for r in rows:
        stars = f"{r['rating']}/5 " if r["rating"] else ""
        who = f" [{r['label'] or r['invite_code']}]" if r["invite_code"] else ""
        print(f"#{r['id']} {r['created_at']:%Y-%m-%d %H:%M}{who} {stars}({r['screen'] or '?'})\n    {r['comment']}")


if __name__ == "__main__":
    main()

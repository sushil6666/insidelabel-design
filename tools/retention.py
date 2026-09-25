#!/usr/bin/env python3
"""
Delete users' scan photos older than 30 days that nothing still needs (D-080, D-098).

Held scans (problem reports, "send it to us"), catalogue versions' photos, scans
under review and photos re-sent recently are kept. Dry run unless --apply.

    INSIDELABEL_DB=… python tools/retention.py                 # what would go
    INSIDELABEL_DB=… python tools/retention.py --apply         # daily, from cron, at deploy
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel import retention  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    ap.add_argument("--days", type=int, default=retention.DAYS)
    ap.add_argument("--apply", action="store_true", help="delete; without it, only list")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    if a.days < retention.DAYS:
        sys.exit(f"--days below {retention.DAYS} would break D-080's promise to reviewers and users")
    if not os.path.isdir(a.media):
        sys.exit(f"no media directory at {a.media}")
    out = retention.run(a.db, LocalMedia(a.media), days=a.days, apply=a.apply)
    if not a.apply:
        print(f"dry run: {len(out['delete'])} photo(s) older than {a.days} days would be deleted "
              "(--apply to delete)")
        for k in out["delete"]:
            print(f"  {k}")
        return
    print(f"deleted {len(out['deleted'])} photo(s); {len(out['missing'])} were already gone (marked)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
The invite-only web beta (D-102): codes for testers, who came back, what they said.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"

    python tools/beta.py invite 1 --label "T01 Priya" --base https://yourdomain.in
        # prints a join link per code: send one link to one person
    python tools/beta.py list                 # each code: devices, scans, days active, last scan
    python tools/beta.py feedback             # newest feedback first
    python tools/beta.py reset CODE           # tester changed phone or cleared the browser
    python tools/beta.py revoke CODE          # lock a code out

One code per person, not per household: the W4 retention number (D-055) is
counted per code. A label is for you only; the app never shows it. A first
name or "T07" is enough - no phone numbers or emails here.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.db.store import Store  # noqa: E402


def _d(ts):
    return ts.strftime("%Y-%m-%d") if ts else "-"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("invite", help="make N codes")
    inv.add_argument("n", type=int)
    inv.add_argument("--label", help="who they are for (you only)")
    inv.add_argument("--base", default=os.environ.get("INSIDELABEL_PUBLIC_URL", "http://127.0.0.1:8000"),
                     help="the site's address, for the join links")
    inv.add_argument("--devices", type=int, default=3, help="devices per code")
    sub.add_parser("list", help="each code: devices, scans, days active")
    fb = sub.add_parser("feedback", help="newest feedback first")
    fb.add_argument("--limit", type=int, default=100)
    for cmd in ("reset", "revoke"):
        sub.add_parser(cmd).add_argument("code")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    store = Store(a.db)

    if a.cmd == "invite":
        if not 1 <= a.n <= 200:
            sys.exit("make 1-200 codes at a time")
        base = a.base.rstrip("/")
        for code in store.create_invites(a.n, label=a.label, max_devices=a.devices):
            print(f"{code}  {base}/app/#/join/{code}")
    elif a.cmd == "list":
        rows = store.beta_testers()
        if not rows:
            print("no invites yet: python tools/beta.py invite 1 --label …")
        for r in rows:
            state = " REVOKED" if r["revoked_at"] else ""
            print(f"{r['code']}  {(r['label'] or '')[:20]:<20} {r['devices']} device(s)  {r['scans']} scan(s)  "
                  f"{r['days_active']} day(s) active  first {_d(r['first_scan'])}  last {_d(r['last_scan'])}  "
                  f"{r['feedback']} feedback  {'agreed ' + _d(r['agreed_at']) if r['agreed_at'] else 'not agreed yet'}"
                  f"{state}")
    elif a.cmd == "feedback":
        rows = store.feedback_list(a.limit)
        if not rows:
            print("no feedback yet")
        for r in rows:
            stars = f"{r['rating']}/5 " if r["rating"] else ""
            who = r["label"] or r["invite_code"] or "no code"
            print(f"#{r['id']} {r['created_at']:%Y-%m-%d %H:%M} [{who}] {stars}({r['screen'] or '?'})\n    {r['comment']}")
    elif a.cmd == "reset":
        print(f"{store.reset_invite(a.code)} device(s) removed from {Store.clean_code(a.code)}; "
              "the tester can open their link again")
    elif a.cmd == "revoke":
        if not store.revoke_invite(a.code):
            sys.exit(f"no invite {a.code}")
        print(f"{Store.clean_code(a.code)} revoked")


if __name__ == "__main__":
    main()

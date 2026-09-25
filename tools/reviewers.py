#!/usr/bin/env python3
"""
Reviewer accounts for the /review screen (D-097): one login per person.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"
    python tools/reviewers.py add sushil          # prints a generated password, once
    python tools/reviewers.py add asha --ask      # type one instead (12+ characters)
    python tools/reviewers.py list
    python tools/reviewers.py reset asha          # new password; old one and old forms stop working
    python tools/reviewers.py disable asha        # locked out at once; past decisions keep the name

Once the first account exists, the shared INSIDELABEL_REVIEW_TOKEN is refused.
Only the hash is stored; a lost password is reset, never recovered.
"""
import argparse
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.review import accounts  # noqa: E402


def _password(ask):
    if not ask:
        return accounts.generate_password(), True
    pw = getpass.getpass("Password (12+ characters): ")
    if pw != getpass.getpass("Again: "):
        sys.exit("The two passwords differ.")
    return pw, False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("add", "reset"):
        p = sub.add_parser(cmd)
        p.add_argument("name")
        p.add_argument("--ask", action="store_true", help="type the password instead of generating one")
    sub.add_parser("disable").add_argument("name")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")

    try:
        if a.cmd in ("add", "reset"):
            pw, made = _password(a.ask)
            (accounts.add if a.cmd == "add" else accounts.set_password)(a.db, a.name, pw)
            print(f"{a.name}: {'added' if a.cmd == 'add' else 'password reset'}.")
            if made:
                print(f"password: {pw}")
                print("Shown once. Give it to the reviewer privately; it is not stored anywhere.")
        elif a.cmd == "disable":
            accounts.disable(a.db, a.name)
            print(f"{a.name}: disabled.")
        else:
            rows = accounts.list_all(a.db)
            if not rows:
                print("no reviewer accounts yet (the shared token still works until the first is added)")
            for r in rows:
                last = r["last_login_at"].strftime("%Y-%m-%d %H:%M") if r["last_login_at"] else "never"
                print(f"{r['name']:<16} {'active' if r['active'] else 'disabled':<9} last login {last}")
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()

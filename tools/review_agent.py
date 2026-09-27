#!/usr/bin/env python3
"""
The review agents (D-117): Gemini drafts queue items, the checker confirms or
sends them to a person. Shadow mode only: drafts are stored and shown on
/review, nothing is published.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"
    python tools/review_agent.py run                    # draft up to 5 open items (PAID: one Gemini call each)
    python tools/review_agent.py run --limit 20
    python tools/review_agent.py run --item 12 --item 13
    python tools/review_agent.py run --include-decided  # also items a person already decided (the measurement set)
    python tools/review_agent.py run --item 12 --replay answer.json   # a recorded answer, no Gemini call
    python tools/review_agent.py show 12                # the newest draft and its checks
    python tools/review_agent.py measure                # the drafts against people's decisions (D-117 point 4)
    python tools/review_agent.py mark-drafted --by claude 3 4 5    # who drafted versions published before 015

On the server: `il tools/review_agent.py ...` (DEPLOY.md). `run` needs
GEMINI_API_KEY, which the tools don't get from settings.env; the systemd
timer (insidelabel-review-agent) has it.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.media import LocalMedia  # noqa: E402
from insidelabel.review import agent  # noqa: E402
from insidelabel.review.draft_prompt import PROMPT_VERSION  # noqa: E402
from insidelabel.review.service import ReviewError, ReviewService  # noqa: E402



def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f} %"


def _show(row):
    print(f"item {row['review_item_id']}  draft {row['id']}  {row['created_at']:%Y-%m-%d %H:%M}  "
          f"{row['drafter']} / prompt {row['prompt_version']}  -> {row['outcome']}")
    if row["error"]:
        print(f"  error: {row['error']}")
    d = row["draft"] or {}
    if d:
        print(f"  category {d.get('category')} ({d.get('category_source')}): {d.get('category_reason')}")
        for x in d.get("ingredients") or []:
            print(f"    | {x}")
        for x in d.get("doubts") or []:
            print(f"  doubt: {x}")
    for c in row["checks"] or []:
        print(f"  [{'ok ' if c['ok'] else 'NO '}] {c['check']}{': ' + c['detail'] if c['detail'] else ''}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="draft and check queue items (shadow)")
    run.add_argument("--limit", type=int, default=5)
    run.add_argument("--item", type=int, action="append", help="these items only")
    run.add_argument("--include-decided", action="store_true")
    run.add_argument("--replay", help="a recorded Gemini answer (JSON file) instead of a call")
    sub.add_parser("show").add_argument("item", type=int)
    sub.add_parser("measure")
    mk = sub.add_parser("mark-drafted")
    mk.add_argument("--by", required=True, choices=["claude", "gemini"])
    mk.add_argument("items", type=int, nargs="+")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    service = ReviewService(a.db, None)           # never publishes, so no engine version needed

    try:
        if a.cmd == "run":
            items = a.item or service.items_to_draft(PROMPT_VERSION, a.limit, a.include_decided)
            if not items:
                print("nothing to draft")
            call = None
            if a.replay:
                text = open(a.replay, encoding="utf-8").read()
                call = lambda _prompt, _images: text          # noqa: E731
            media = LocalMedia(a.media)
            for item_id in items:
                row = agent.draft_item(service, media, item_id, mode="shadow", call=call)
                failed = [c["check"] for c in row["checks"] or [] if not c["ok"]]
                print(f"item {item_id}: {row['outcome']}"
                      + (f" ({', '.join(failed)})" if failed else "")
                      + (f" {row['error']}" if row["error"] else ""))
        elif a.cmd == "show":
            row = service.latest_draft(a.item)
            if row is None:
                sys.exit(f"no draft for item {a.item}")
            _show(row)
        elif a.cmd == "measure":
            r = agent.measure(service)
            print(f"decided items with a draft: {r['items']} ({r['published']} published, {r['rejected']} rejected)")
            print(f"  category agrees:     {_pct(r['category'])}")
            print(f"  ingredients agree:   {_pct(r['ingredients'])}")
            print(f"  front claims agree:  {_pct(r['claims'])}")
            print(f"  confirmed by the checker but corrected by a person: {r['confirmed_but_corrected'] or 'none'}")
            for who, b in sorted(r["by_final_drafter"].items()):
                print(f"  published records drafted by {who}: {b['agree']} of {b['items']} agree")
            for d in r["disagreements"]:
                print(f"  item {d['id']}: {d['decision']}"
                      + ("" if d["decision"] == "rejected" else
                         f" (category {'ok' if d['category'] else 'differs'},"
                         f" ingredients {'ok' if d['ingredients'] else 'differ'},"
                         f" claims {'ok' if d['claims'] else 'differ'})"))
            print(f"gate (at least {agent.GATE['items']} items, {_pct(agent.GATE['agreement'])} agreement, "
                  f"no confirmed-but-corrected): {'PASSES' if r['gate_passes'] else 'not yet'}")
        else:
            done = service.mark_drafted(a.items, a.by)
            print(f"marked drafted_by={a.by}: {done or 'nothing'}")
            skipped = sorted(set(a.items) - set(done))
            if skipped:
                print(f"not marked (not published by a person, or already marked): {skipped}")
    except (ReviewError, ValueError) as e:
        sys.exit(str(e))
    except json.JSONDecodeError as e:
        sys.exit(f"--replay: {e}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Reproduce a reported problem (D-092).

A report carries the phone's trail (screens, API calls with request ids,
errors) and is tied to the scans it touched. Each scan row keeps the model's
raw answer, the request options, the build and the data version, and its
photos are held past retention. This tool puts it together and replays every
scan on today's code, with storage off, so nothing is written.

    export INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql"

    python tools/repro.py list                    # open reports, newest first
    python tools/repro.py show 12                 # timeline + replay + what differs
    python tools/repro.py show 12 --save kid-retake-loop
        # freeze scan(s) as tests/regression/problems/kid-retake-loop.json:
        # edit "expected" to what it SHOULD show, then fix the code until
        # tests/test_problem_regressions.py passes
    python tools/repro.py close 12 fixed --note "headline order, see D-091"
"""
import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel import repro  # noqa: E402
from insidelabel.db.store import Store  # noqa: E402
from insidelabel.extraction.providers import gemini  # noqa: E402
from insidelabel.media import LocalMedia  # noqa: E402

REGRESSIONS = os.path.join(ROOT, "tests", "regression", "problems")
STATUSES = ("reproduced", "fixed", "not_a_bug", "duplicate", "open")


def _ts(ms_or_dt, t0=None):
    if isinstance(ms_or_dt, dt.datetime):
        return ms_or_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"+{(ms_or_dt - t0) / 1000:6.1f}s" if t0 else str(ms_or_dt)


def event_line(e, t0):
    t = _ts(e.get("t", 0), t0)
    kind = e.get("type")
    if kind == "api":
        extra = f" {e.get('error')}" if e.get("error") else ""
        return f"{t}  api     {e.get('method')} {e.get('path')} → {e.get('status')}{extra} " \
               f"({e.get('ms')} ms) req {e.get('request_id')}"
    if kind == "route":
        return f"{t}  screen  {e.get('to')}" + (f"/{e['arg']}" if e.get("arg") else "")
    rest = {k: v for k, v in e.items() if k not in ("t", "type")}
    return f"{t}  {kind:<7} {json.dumps(rest, ensure_ascii=False)}"


def show(store, media, pid, save=None):
    got = store.problem(pid)
    if got is None:
        sys.exit(f"no problem report #{pid}")
    rep, scans = got["report"], got["scans"]
    print(f"Problem #{rep['id']} · {rep['kind']} · {rep['status']} · {_ts(rep['created_at'])}")
    if rep["comment"]:
        print(f"  says: {rep['comment']}")
    print(f"  app {rep['app_version']} · server build {rep['build']} · data {rep['data_version']}")
    if rep["signature"]:
        print(f"  signature: {rep['signature']}")
    c = rep["client"] or {}
    if c:
        print(f"  phone: {c.get('ua')}  screen {c.get('screen')}  network {c.get('network')}  "
              f"barcode reader {c.get('barcode_detector')}  profiles {c.get('profiles')}")
    if rep["server_error"]:
        print("\n  server traceback:\n    " + rep["server_error"].strip().replace("\n", "\n    "))

    events = rep["events"] or []
    if events:
        t0 = events[0].get("t", 0)
        print(f"\nTrail ({len(events)} events, oldest first):")
        for e in events:
            print("  " + event_line(e, t0))

    shown_by_rid = {e.get("request_id"): e.get("shown") for e in events
                    if e.get("type") == "api" and e.get("path") == "/scan"}
    saved = []
    print(f"\nScans tied to this report: {len(scans)}")
    for s in scans:
        print(f"\n  scan {s['id']} · {s['outcome']}{' (' + s['error_code'] + ')' if s['error_code'] else ''}"
              f" · req {s['request_id']} · {_ts(s['created_at'])}")
        print(f"    ran build {s['build']} · data {s['data_version']} · engine {s['engine_version']} · "
              f"prompt {s['prompt_version']} · timings {s['timings']}")
        print(f"    request {json.dumps(s['request'])}")
        for line in repro.read_lines(s.get("timings"), s.get("request")):    # D-193
            print(f"    {line}")
        print(f"    photos back={s['back_image_key']} front={s['front_image_key']} hold={s['evidence_hold']}")
        if s.get("model_error"):                                           # D-172
            print(f"    model error {s['model_error']}")
        check = ((s.get("ocr") or {}).get("back") or {}).get("independent_read")
        if check:                                                         # D-159: the D-118 gate's reading
            print(f"    independent read {json.dumps(check)}")
        hit = store.version_hit(s["product_version_id"]) if s["cache_hit"] and s["product_version_id"] else None
        out = repro.replay_scan(s, media, hit)
        for n in out["notes"]:
            print(f"    note: {n}")
        if out["status"] is None:
            continue
        now = repro.summary(out["screen"])
        # An error without a screen (a 503, say): print the server's own error instead.
        err = None if now else (out.get("body") or {}).get("detail", out.get("body"))
        print(f"    replay → HTTP {out['status']}: {json.dumps(now or err, ensure_ascii=False)}")
        diff = repro.compare(shown_by_rid.get(s["request_id"]), now)
        print("    same as what the user saw" if not diff else "    DIFFERS from what the user saw:")
        for d in diff:
            print(f"      {d}")
        # D-172: a blocked answer has no reading to keep as a regression case.
        if save and s["model_raw"] and not s["cache_hit"] and not gemini.blocked_reason(s["model_raw"]):
            saved.append(s)

    if save:
        write_regression(save, rep, saved)


def write_regression(name, rep, scans):
    """Freeze scans as a test. Photos are left out (EXIF, git); the test uses a 1x1 PNG."""
    if not scans:
        sys.exit("nothing to save: no replayable vision scan in this report")
    os.makedirs(REGRESSIONS, exist_ok=True)
    cases = []
    for s in scans:
        req = s["request"] or {}
        files = {r: (f"{r}.png", repro.PNG, "image/png") for r in (req.get("images") or ["back"])}
        now = repro.post_scan(repro.form_for(req, s["model_raw"]), files, s.get("ocr"))
        cases.append({"scan_id": str(s["id"]), "request": req, "model_raw": s["model_raw"],
                      "ocr": s.get("ocr") or {},
                      "expected_status": now["status"], "expected": repro.summary(now["screen"])})
    path = os.path.join(REGRESSIONS, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"problem_id": rep["id"], "comment": rep["comment"], "saved_on": dt.date.today().isoformat(),
                   "note": "expected = today's output. Edit it to what the screen SHOULD show; "
                           "the test then fails until the fix lands.",
                   "cases": cases}, f, indent=1, ensure_ascii=False)
    print(f"\nSaved {len(cases)} case(s) to {os.path.relpath(path, ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--media", default=os.environ.get("INSIDELABEL_MEDIA", os.path.join(ROOT, "media")))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="open problem reports")
    sh = sub.add_parser("show", help="timeline, versions and a replay of every scan")
    sh.add_argument("id", type=int)
    sh.add_argument("--save", metavar="NAME", help="freeze as tests/regression/problems/NAME.json")
    cl = sub.add_parser("close", help="set a report's status")
    cl.add_argument("id", type=int)
    cl.add_argument("status", choices=STATUSES)
    cl.add_argument("--note")
    a = ap.parse_args(argv)
    if not a.db:
        sys.exit("set INSIDELABEL_DB or pass --db")
    store = Store(a.db)

    if a.cmd == "list":
        rows = store.open_problems()
        if not rows:
            print("no open problem reports")
        for r in rows:
            what = r["comment"] or r["signature"] or ""
            print(f"#{r['id']:<5} {r['kind']:<6} {_ts(r['created_at'])}  {what[:70]}"
                  f"{'  scan ' + str(r['scan_id']) if r['scan_id'] else ''}")
    elif a.cmd == "show":
        media = LocalMedia(a.media) if os.path.isdir(a.media) else None
        show(store, media, a.id, save=a.save)
    elif a.cmd == "close":
        if not store.set_problem_status(a.id, a.status, a.note):
            sys.exit(f"no problem report #{a.id}")
        print(f"#{a.id} → {a.status}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One JSON snapshot of how InsideLabel stands, for the health report page.

    python tools/health_report.py --out <scratch>/health.json            # runs the tests too
    python tools/health_report.py --out <scratch>/health.json --no-tests
    INSIDELABEL_DB=... python tools/health_report.py --out ...           # adds catalogue, scans, review
    il tools/health_report.py --no-tests --out /tmp/health.json          # on the server (DEPLOY.md)

Why a snapshot and not a live page: Sushil asked for the project's own output
laid out like an Elementary report (2026-09-28). The numbers already exist in
three places (pytest, tools/release_check.py, the database); this gathers them
without a second implementation of any of them. Gates come from release_check's
own functions, the D-117 agreement from review.agent.measure(), so the page can
never disagree with the tools it summarises.

Counts only. No user id, invite code, photo key, device id or profile leaves
the database through this file, so the snapshot can be published or pasted.
A gate with no data stays TODO, never PASS (CLAUDE.md).
"""
import argparse
import collections
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import release_check  # noqa: E402
from insidelabel.core import engine  # noqa: E402
from insidelabel.lenses import allergens  # noqa: E402


def _git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tests():
    """Run pytest once with a JUnit file; count outcomes per test file."""
    with tempfile.TemporaryDirectory() as tmp:
        xml = os.path.join(tmp, "junit.xml")
        # Never hand the tests INSIDELABEL_DB (see release_check.py): they would write into it.
        env = {k: v for k, v in os.environ.items() if k != "INSIDELABEL_DB"}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}"],
                           cwd=ROOT, capture_output=True, text=True, env=env)
        if not os.path.exists(xml):
            return {"status": "error", "summary": (r.stdout.strip().splitlines() or ["no output"])[-1]}
        tree = ET.parse(xml)
    counts = collections.Counter()
    by_file = collections.defaultdict(collections.Counter)
    failures, slowest = [], []
    for case in tree.iter("testcase"):
        cls = case.get("classname", "")
        name = f"{cls}.{case.get('name')}"
        path = cls.split(".")
        mod = path[1] if path[0] == "tests" and len(path) > 1 else path[0]
        mod = "regression" if mod == "regression" else mod
        skipped = case.find("skipped")
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
            node = case.find("failure") if case.find("failure") is not None else case.find("error")
            failures.append({"test": name, "message": (node.get("message") or "")[:300]})
        elif skipped is not None:
            outcome = "xfailed" if "xfail" in (skipped.get("type") or "") else "skipped"
        else:
            outcome = "passed"
        counts[outcome] += 1
        by_file[mod][outcome] += 1
        slowest.append((float(case.get("time") or 0), name))
    slowest.sort(reverse=True)
    return {
        "status": "pass" if r.returncode == 0 else "fail",
        "summary": (r.stdout.strip().splitlines() or [""])[-1],
        "counts": dict(counts),
        "total": sum(counts.values()),
        "by_file": {k: dict(v) for k, v in sorted(by_file.items())},
        "failures": failures,
        "slowest": [{"test": n, "seconds": round(t, 2)} for t, n in slowest[:8]],
    }


def gates(uri):
    sections = [("Accuracy and data", release_check.gates(os.path.join(ROOT, "gold"),
                                                          os.path.join(ROOT, "predictions"))),
                ("Decisions", release_check.decision_gates())]
    sections.append(("Catalogue", release_check.catalogue_gates(uri) if uri else
                     [(release_check.TODO, "Catalogue gates", "no database given (INSIDELABEL_DB)")]))
    return [{"section": s, "status": st, "name": n, "detail": d}
            for s, rows in sections for st, n, d in rows]


def data_tables():
    rows = [a for a in engine.ADDITIVES["additives"] if a.get("class") != "note"]
    return {
        "additives": len(rows),
        "additives_by_status": dict(collections.Counter(a.get("fssai_status", "missing") for a in rows)),
        "additives_by_concern": dict(collections.Counter(a["concern"] for a in rows)),
        "additives_with_basis": sum(1 for a in rows if a.get("fssai_basis") and a.get("verified_on")),
        "last_verified": max((a.get("verified_on") or "") for a in rows) or None,
        "nova_markers": len(engine.NOVA["markers"]),
        "allergens": len(allergens.ALLERGENS),
        "sugar_names": len(engine._SUGAR_ALIASES),
    }


def database(uri):
    import psycopg
    from insidelabel.review import agent
    from insidelabel.review.service import ReviewService

    q = {
        "products": "SELECT count(*) FROM products",
        "versions_by_status": "SELECT status, count(*) FROM product_versions GROUP BY 1",
        "queue_by_status": "SELECT status, count(*) FROM review_queue GROUP BY 1",
        "queue_by_kind": "SELECT kind, count(*) FROM review_queue WHERE status IN ('open','claimed') GROUP BY 1",
        "scans_by_outcome": "SELECT outcome, count(*) FROM scans GROUP BY 1",
        "scans_by_day": """SELECT to_char(created_at AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD'), outcome, count(*)
                             FROM scans WHERE created_at > now() - interval '14 days' GROUP BY 1, 2 ORDER BY 1""",
        "latency_ms": """SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
                                percentile_cont(0.9) WITHIN GROUP (ORDER BY latency_ms)
                           FROM scans WHERE latency_ms IS NOT NULL AND NOT cache_hit""",
        "categories_published": """SELECT k.code, count(*) FROM products p JOIN categories k ON k.id = p.category_id
                                     JOIN product_versions v ON v.product_id = p.id AND v.is_current
                                    GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12""",
        "problem_reports": "SELECT count(*) FROM problem_reports",
        "corrections": "SELECT count(*) FROM corrections",
    }
    out = {}
    with psycopg.connect(uri) as c:
        for k, sql in q.items():
            res = c.execute(sql).fetchall()
            if k == "scans_by_day":
                days = collections.defaultdict(dict)
                for day, outcome, n in res:
                    days[day][outcome] = n
                out[k] = [{"day": d, **v} for d, v in sorted(days.items())]
            elif k == "latency_ms":
                p50, p90 = res[0]
                out[k] = {"p50": round(p50) if p50 else None, "p90": round(p90) if p90 else None}
            elif len(res[0]) == 1 if res else False:
                out[k] = res[0][0]
            else:
                out[k] = {str(a): b for a, b in res}
    service = ReviewService(uri, None)
    try:
        m = agent.measure(service)
    except psycopg.errors.UndefinedTable as e:
        # A database behind on migrations (the laptop's, before 015): say so, don't guess.
        out["review_agents"] = {"unavailable": f"{e.diag.message_primary}; run db.migrate"}
        return out
    out["review_agents"] = {
        "items": m["items"], "published": m["published"], "rejected": m["rejected"],
        "category": m["category"], "ingredients": m["ingredients"], "claims": m["claims"],
        "agree": sum(1 for r in [agent.compare(x) for x in service.decided_with_drafts()] if r["agrees"]),
        "confirmed_but_corrected": m["confirmed_but_corrected"],
        "gate": agent.GATE, "gate_passes": m["gate_passes"],
    }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="where to write the JSON (a scratch path, not reports/)")
    ap.add_argument("--no-tests", action="store_true", help="skip the test run (e.g. on the server)")
    ap.add_argument("--db", default=os.environ.get("INSIDELABEL_DB"))
    ap.add_argument("--source", default="laptop", help="a label for where this ran: laptop, server")
    a = ap.parse_args(argv)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": a.source,
        "git": {"commit": _git("rev-parse", "--short", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD")},
        "tests": None if a.no_tests else tests(),
        "gates": gates(a.db),
        "manual_items": release_check.MANUAL_ITEMS,
        "data": data_tables(),
        "database": database(a.db) if a.db else None,
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    g = collections.Counter(x["status"] for x in report["gates"])
    t = report["tests"]
    print(f"wrote {a.out}: gates {dict(g)}" + (f"; tests {t['counts']}" if t and t.get("counts") else ""))


if __name__ == "__main__":
    main()

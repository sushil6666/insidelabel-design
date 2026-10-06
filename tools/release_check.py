#!/usr/bin/env python3
"""
Release gate for the closed beta (blueprint §15, D-007). Prints every gate as
PASS / FAIL / TODO and exits 1 if any computed gate fails, so it can run in CI.

    python tools/release_check.py                 # data + accuracy gates
    python tools/release_check.py --with-tests    # also runs the test suite
    INSIDELABEL_DB=... python tools/release_check.py   # also catalogue gates

Computed gates compare gold/ (hand transcriptions) with predictions/ (what the
model read). They measure the whole pipeline on real packs; they are only as
meaningful as the size of the gold set, which is itself the first gate.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from insidelabel.claims import checker  # noqa: E402
from insidelabel.core import engine  # noqa: E402
from insidelabel.lenses import nutrition  # noqa: E402
from insidelabel.core.tokenize import extract_ins  # noqa: E402
from insidelabel.lenses import allergens  # noqa: E402

PASS, FAIL, TODO, MANUAL = "PASS", "FAIL", "TODO", "MANUAL"
FLAGGED = {"contains", "may_contain"}

# Blueprint §15 thresholds.
MIN_GOLD = 20
MIN_INGREDIENT_MATCH = 0.95
MIN_NUTRITION_MATCH = 0.98          # D-133: nutrition numbers read correctly
MAX_FALSE_CONTRADICTION_RATE = 0.01
MIN_PUBLISHED = 50
DECISIONS_BEFORE_RELEASE = ["D-051", "D-052", "D-055"]
# D-058 seed: sweet biscuits/cookies (7.2.1) and wafers etc. (7.2.2); not 7.2.3 "mixes".
BISCUIT_CATEGORIES = ["7.2.1", "7.2.2"]


def norm(s):
    s = re.sub(r"[^a-z0-9%() ]", " ", s.lower().strip())
    return re.sub(r"\s+", " ", s).strip()


def ins_of(ingredients):
    return {i for t in engine.tokenize(", ".join(ingredients)) if (i := extract_ins(t))}


def f1(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    r = tp / len(gold) if gold else 1.0
    return 2 * p * r / (p + r) if p + r else 0.0


def load(path):
    out = {}
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out[os.path.basename(f)[:-5]] = json.load(fh)
    return out


def contradictions(label):
    raw = ", ".join(label.get("ingredients") or [])
    if not raw:
        return set(), 0
    v = engine.analyze(raw)
    cc = checker.check_claims(label.get("front_claims") or [], raw, v)
    return {c["rule_id"] for c in cc["checked"] if c["contradicted"]}, len(cc["checked"])


def gates(gold_dir, pred_dir):
    gold, pred = load(gold_dir), load(pred_dir)
    ids = sorted(set(gold) & set(pred))
    out = []

    n = len(gold)
    out.append((PASS if n >= MIN_GOLD else FAIL, "Gold set size",
                f"{n} hand-transcribed labels (need ≥ {MIN_GOLD}; a third shot in bad conditions)"))
    missing = sorted(set(gold) - set(pred))
    if missing:
        out.append((TODO, "Gold labels without a prediction", ", ".join(missing)))

    halluc, flips, ing_f1, allergen_miss, fp, checked = [], [], [], [], 0, 0
    for i in ids:
        g, p = gold[i], pred[i]
        extra = ins_of(p.get("ingredients") or []) - ins_of(g.get("ingredients") or [])
        if extra:
            halluc.append(f"{i}: INS {', '.join(sorted(extra))}")
        gb = engine.analyze(", ".join(g["ingredients"]))["binary"] if g.get("ingredients") else None
        pb = engine.analyze(", ".join(p["ingredients"]))["binary"] if p.get("ingredients") else None
        if gb != pb:
            flips.append(f"{i}: {gb} → {pb}")
        ing_f1.append(f1({norm(x) for x in p.get("ingredients") or []},
                         {norm(x) for x in g.get("ingredients") or []}))

        codes = list(allergens.ALLERGENS)
        ga = allergens.check(g.get("ingredients") or [], g.get("allergen_statement"), codes)
        pa = allergens.check(p.get("ingredients") or [], p.get("allergen_statement"), codes,
                             confidence=(p.get("confidence") or {}).get("ingredients", 0.0))
        for c in codes:
            # A miss: the pack declares it, and we'd tell the parent it isn't listed.
            # cannot_confirm / uncertain are refusals, not misses.
            if ga[c].state in FLAGGED and pa[c].state == "not_listed":
                allergen_miss.append(f"{i}: {c}")

        gc, _ = contradictions(g)
        pc, k = contradictions(p)
        fp += len(pc - gc)
        checked += k

    out.append((PASS if not halluc else FAIL, "Hallucinated INS numbers = 0",
                "; ".join(halluc) or f"none across {len(ids)} labels"))
    out.append((PASS if not flips else FAIL, "Verdict flips = 0", "; ".join(flips) or "none"))
    mean_f1 = sum(ing_f1) / len(ing_f1) if ing_f1 else 0.0
    out.append((PASS if mean_f1 >= MIN_INGREDIENT_MATCH else FAIL,
                f"Ingredient match ≥ {MIN_INGREDIENT_MATCH:.0%}", f"mean ingredient F1 {mean_f1:.3f}"))
    out.append((PASS if not allergen_miss else FAIL, "Allergen misses = 0",
                "; ".join(allergen_miss) or f"none ({len(ids)} labels × {len(allergens.ALLERGENS)} allergens)"))
    rate = fp / checked if checked else 0.0
    # No gold claim matched a rule -> nothing was measured. Never report that as a pass.
    out.append((TODO if not checked else PASS if rate < MAX_FALSE_CONTRADICTION_RATE else FAIL,
                f"False contradictions < {MAX_FALSE_CONTRADICTION_RATE:.0%}",
                f"{fp} of {checked} checked claims ({rate:.1%})" if checked else
                "unmeasured: no front claim on the gold labels matches a claim rule yet - "
                "add packs claiming 'no added sugar' / 'no preservatives' / 'made with real X'"))

    # D-133: the nutrition table, number by number. Predictions made before the
    # table was read have none, and that is unmeasured, never a pass.
    scored = [nutrition.accuracy(gold[i].get("nutrition"), pred[i].get("nutrition")) for i in ids]
    scored = [x for x in scored if x]
    right, total = sum(x[0] for x in scored), sum(x[1] for x in scored)
    share = right / total if total else 0.0
    out.append((TODO if not scored else PASS if share >= MIN_NUTRITION_MATCH else FAIL,
                f"Nutrition numbers read correctly ≥ {MIN_NUTRITION_MATCH:.0%}",
                f"{right} of {total} numbers on {len(scored)} labels ({share:.1%})" if scored else
                "unmeasured: no prediction has a nutrition table yet - re-run the gold set with the D-133 "
                "prompt (a paid read per label)"))

    # Every INS on a gold label is in the table, so none reaches a user unflagged.
    rows = engine._ADDITIVE_BY_INS
    unknown = sorted({x for g in gold.values() for x in ins_of(g.get("ingredients") or [])} - set(rows))
    out.append((PASS if not unknown else FAIL, "Every gold INS has an additives.json row",
                ", ".join(unknown) or "yes"))
    unverified = sorted(a["ins"] for a in engine.ADDITIVES["additives"] if a.get("verify"))
    out.append((PASS if not unverified else FAIL, "No additive row still marked verify:true",
                ", ".join(unverified) or "none"))
    return out


def decision_gates():
    with open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8") as f:
        text = f.read()
    out = []
    for d in DECISIONS_BEFORE_RELEASE:
        m = re.search(rf"^### {d} · (.+)$", text, re.M)
        head = m.group(1) if m else "missing"
        decided = m and ("`LOCKED`" in head or "SUPERSEDED" in head)
        out.append((PASS if decided else FAIL, f"{d} decided", head))
    return out


def catalogue_gates(uri):
    import psycopg
    with psycopg.connect(uri) as c:
        published = c.execute("SELECT count(*) FROM product_versions WHERE is_current").fetchone()[0]
        uncategorised = c.execute("""SELECT count(*) FROM products p JOIN product_versions v
                                       ON v.product_id = p.id AND v.is_current
                                    WHERE p.category_id IS NULL""").fetchone()[0]
        kids = c.execute("""SELECT count(*) FROM products p JOIN categories k ON k.id = p.category_id
                             JOIN product_versions v ON v.product_id = p.id AND v.is_current
                            WHERE k.code = ANY(%s)""", (BISCUIT_CATEGORIES,)).fetchone()[0]
        waiting = c.execute("SELECT count(*) FROM review_queue WHERE status IN ('open','claimed')").fetchone()[0]
    return [
        (PASS if published >= MIN_PUBLISHED else FAIL, f"Published catalogue ≥ {MIN_PUBLISHED} SKUs",
         f"{published} published, {waiting} waiting for review"),
        (PASS if kids >= 15 else (TODO if uncategorised else FAIL), "≥ 15 kids' biscuits published (D-058)",
         f"{kids} in categories {' / '.join(BISCUIT_CATEGORIES)}" + (f"; {uncategorised} published products have no category yet"
                                        if uncategorised else "")),
    ]


MANUAL_ITEMS = [
    "PWA: camera + barcode, result screen per D-060 to D-066, profiles, compare, report a mistake",
    "Deployment: host with PostgreSQL 19, HTTPS, R2 photo store, backups; tools/retention.py --apply daily from cron (D-080, D-098)",
    "Reviewer accounts on the deployed server (tools/reviewers.py, D-097), so the shared token is refused",
    "'Send it to us' tried on a phone: two refused scans → sent → published → shown on open (D-070, D-096)",
    "Privacy policy (DPDP Act; children's data, parental consent - D-074)",
    "Conflict-of-interest policy, methodology page, who is behind the app, 'last verified' dates (D-076)",
    "Play Console: developer account verified (D-011), closed-testing requirement met, target audience adults",
    "Rate limits (D-095): one server process (or shared counters), INSIDELABEL_PROXY_HOPS set behind the proxy",
    "Beta access (D-162): INSIDELABEL_INVITE_ONLY=off on the deploy on purpose; the daily photo limit (D-148) and per-IP limits (D-095) on; testers opted in through the Play closed test",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=os.path.join(ROOT, "gold"))
    ap.add_argument("--pred", default=os.path.join(ROOT, "predictions"))
    ap.add_argument("--with-tests", action="store_true")
    args = ap.parse_args()

    sections = [("Accuracy & data", gates(args.gold, args.pred)), ("Decisions", decision_gates())]
    uri = os.environ.get("INSIDELABEL_DB")
    sections.append(("Catalogue", catalogue_gates(uri) if uri else
                     [(TODO, "Catalogue gates", "set INSIDELABEL_DB to check the catalogue")]))
    if args.with_tests:
        # Never hand the tests INSIDELABEL_DB: with it, the app under test writes scans, users and
        # problem reports into that real database (2026-09-28, the laptop's: 386 rows).
        env = {k: v for k, v in os.environ.items() if k != "INSIDELABEL_DB"}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True, env=env)
        last = (r.stdout.strip().splitlines() or ["no output"])[-1]
        sections.append(("Tests", [(PASS if r.returncode == 0 else FAIL, "Test suite", last)]))

    failed = 0
    print("\nINSIDELABEL - BETA RELEASE GATE\n" + "=" * 72)
    for title, rows in sections:
        print(f"\n{title}")
        for status, name, detail in rows:
            failed += status == FAIL
            print(f"  [{status:4}] {name}\n          {detail}")
    print("\nManual (not computed - tick off in STATE.md §11)")
    for m in MANUAL_ITEMS:
        print(f"  [ ]    {m}")
    print("\n" + ("NOT READY: %d gate(s) failing." % failed if failed else "All computed gates pass."))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

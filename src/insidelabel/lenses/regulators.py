"""
regulators.py - India vs EU vs US, information only (D-086).

The verdict, the score and every concern level use FSSAI rules only. This lens
answers a separate, optional question the user asks for: "how do the EU and
the US treat the additives in this pack?" It reads the engine's output and
data/regulatory_status.json, and changes neither.

Display text is built from the status_text templates in the table, never
written per row, so every sentence passes the D-042 wording lint.
"""

import json
import os
import re

DATA_DIR = os.environ.get("INSIDELABEL_DATA", os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")))

with open(os.path.join(DATA_DIR, "regulatory_status.json"), encoding="utf-8") as _f:
    _TABLE = json.load(_f)

META = _TABLE["_meta"]
JURISDICTIONS = list(META["jurisdictions"])          # display order: IN first
DOCS = META["documents"]
ROWS = {r["ins"]: r for r in _TABLE["additives"]}

BASIS = ("The result above uses Indian (FSSAI) rules only. This comparison is "
         "for information and does not change it.")

_INS_IN_FLAG = re.compile(r"\bINS (\w+)")


def _text(entry):
    return META["status_text"][entry["status"]].format(**entry)


def _allowed(entry):
    return entry["status"].startswith("permitted")


def row(ins):
    """Comparison for one INS number, or None if it has not been checked."""
    r = ROWS.get(ins)
    if r is None:
        return None
    regs = {}
    for j in JURISDICTIONS:
        e = r.get(j)
        if e is None:
            regs[j] = {"name": META["jurisdictions"][j], "status": "not_checked",
                       "text": "Not yet checked", "source": None, "reason": None}
            continue
        doc = DOCS[e["doc"]]
        regs[j] = {
            "name": META["jurisdictions"][j],
            "status": e["status"],
            "text": _text(e),
            "reason": e.get("reason"),
            "source": {"title": doc["title"], "url": doc["url"]},
        }
    checked = [r[j] for j in JURISDICTIONS if j in r]
    return {
        "ins": ins,
        "name": r["name"],
        # "differs" compares whether each checked regulator allows it at all;
        # a warning or a single-food permission counts as allowed.
        "differs": len({_allowed(e) for e in checked}) > 1,
        "regulators": regs,
        "verified_on": r["verified_on"],
    }


def ins_in_verdict(verdict):
    """INS numbers the engine matched, from its own flags, in flag order."""
    seen = []
    for f in verdict.get("flags", []):
        if f.get("type") != "additive":
            continue
        m = _INS_IN_FLAG.search(f.get("matched_as", ""))
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def compare(verdict):
    """
    The optional comparison block for a verdict. Additives where the
    regulators differ come first; additives found but not in the table are
    listed as not yet compared, never guessed.
    """
    found = ins_in_verdict(verdict)
    rows = [row(i) for i in found if i in ROWS]
    rows.sort(key=lambda r: not r["differs"])
    return {
        "basis": BASIS,
        "jurisdictions": {j: META["jurisdictions"][j] for j in JURISDICTIONS},
        "additives": rows,
        "differs_count": sum(r["differs"] for r in rows),
        "not_yet_compared": [i for i in found if i not in ROWS],
    }

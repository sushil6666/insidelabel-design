"""
Inside Label - claim checker.

Compares verbatim front-of-pack claims against the engine's output and returns
the contradicting ingredient facts as pairs. No editorial language anywhere:
the output is (claim as printed, ingredient fact), and the user decides what
that means.

Reads engine.py and its data tables; writes to neither. It uses the engine's
own tokenizer so "what counts as an ingredient" can never drift between the
verdict and the claim check.
"""

import json
import os
import re

import engine

_HERE = os.path.dirname(__file__)

with open(os.path.join(_HERE, "data", "claim_rules.json"), "r", encoding="utf-8") as _f:
    RULES = json.load(_f)

with open(os.path.join(engine.DATA_DIR, "additives.json"), "r", encoding="utf-8") as _f:
    _ADDITIVES = json.load(_f)["additives"]

# INS -> additive row, for looking up functional class from an engine flag.
_ADDITIVE_BY_INS = {a["ins"]: a for a in _ADDITIVES if a.get("class") != "note"}
_PRESERVATIVE_INS = {ins for ins, a in _ADDITIVE_BY_INS.items() if a["class"] == "preservative"}

# Added sugar for CLAIM purposes = the engine's hidden-sugar alias list minus
# the entries parked as legally adjacent (see claim_rules.json _meta).
_ADJACENT = set(RULES["added_sugar_adjacent"])
_ADDED_SUGAR_DIRECT = {
    s.lower() for s in engine.NORM["sugar_aliases"]["added_sugar"]
} - _ADJACENT

_FLAVOUR_WORDS = RULES["flavour_carrier_words"]
_NAMED_PRESERVATIVES = RULES["preservative_named_without_ins"]

_INS_IN_MATCH = re.compile(r"INS\s+(\d{3}[a-z]?)", re.IGNORECASE)


def _norm(text):
    """Lowercase, collapse whitespace, drop asterisks and punctuation noise."""
    t = text.lower().replace("*", " ")
    t = re.sub(r"[^a-z0-9%\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _match_rule(claim_text):
    """Return (rule, subject) for the first rule this claim matches, else None."""
    n = _norm(claim_text)
    for rule in RULES["rules"]:
        for phrase in rule.get("match", []):
            if phrase in n:
                return rule, None
        rx = rule.get("match_regex")
        if rx:
            m = re.search(rx, n)
            if m:
                return rule, m.groupdict().get("subject", "").strip()
    return None, None


# ---------------------------------------------------------------------------
# Checks. Each returns a list of fact dicts. Empty list = no contradiction.
# ---------------------------------------------------------------------------
def _check_added_sugar(result, tokens, subject):
    facts = []
    for name in result.get("hidden_sugar_names", []):
        if name in _ADDED_SUGAR_DIRECT:
            facts.append({
                "fact": f"Ingredient list contains {name}.",
                "evidence": name,
                "evidence_type": "ingredient",
                "engine_field": "hidden_sugar_names",
            })
    return facts


def _adjacent_sugar_notes(result):
    """Reported alongside, never as a contradiction. See claim_rules.json _meta."""
    notes = []
    for name in result.get("hidden_sugar_names", []):
        if name in _ADJACENT:
            notes.append({
                "fact": f"Ingredient list contains {name}.",
                "evidence": name,
                "evidence_type": "ingredient",
                "engine_field": "hidden_sugar_names",
                "relation": "adjacent",
                "reason": (
                    "Counted by the hidden-sugar heuristic but not a sugar under "
                    "the added-sugar definition. Reported separately, not as a "
                    "contradiction of the claim."
                ),
            })
    return notes


def _check_preservative(result, tokens, subject):
    facts = []
    seen = set()
    for f in result.get("flags", []):
        m = _INS_IN_MATCH.search(f.get("matched_as", ""))
        if not m:
            continue
        ins = m.group(1).lower()
        if ins in _PRESERVATIVE_INS and ins not in seen:
            seen.add(ins)
            facts.append({
                "fact": f"Ingredient list contains INS {ins} ({_ADDITIVE_BY_INS[ins]['name']}), a preservative.",
                "evidence": f["matched_as"],
                "evidence_type": "additive",
                "engine_field": "flags",
            })
    for tok in tokens:
        for named in _NAMED_PRESERVATIVES:
            if named in tok and named not in seen:
                seen.add(named)
                facts.append({
                    "fact": f"Ingredient list contains {named}, a preservative.",
                    "evidence": tok,
                    "evidence_type": "ingredient",
                    "engine_field": None,
                })
    return facts


def _check_real_subject(result, tokens, subject):
    if not subject:
        return []
    subject = subject.strip()
    synonyms = RULES["real_subject_synonyms"].get(subject, [subject])
    hits = [t for t in tokens if any(s in t for s in synonyms)]

    if not hits:
        return [{
            "fact": f"'{subject}' does not appear in the ingredient list.",
            "evidence": None,
            "evidence_type": "absence",
            "engine_field": None,
        }]

    flavour_only = all(
        any(w in h for w in _FLAVOUR_WORDS) for h in hits
    )
    if flavour_only:
        return [{
            "fact": f"'{subject}' appears in the ingredient list only as: {', '.join(hits)}.",
            "evidence": hits[0],
            "evidence_type": "flavouring",
            "engine_field": None,
        }]
    return []


_CHECKS = {
    "added_sugar_present": _check_added_sugar,
    "preservative_present": _check_preservative,
    "subject_absent_or_flavour_only": _check_real_subject,
}


# ---------------------------------------------------------------------------
def check_claims(front_claims, raw_ingredients, result, front_status="read"):
    """
    front_claims    : list[str], verbatim from the front of pack
    raw_ingredients : the same string that was passed to engine.analyze()
    result          : the dict engine.analyze() returned
    front_status    : "read" | "not_provided" | "unreadable" | "pairing_unverified"

                      "pairing_unverified" means the front WAS read, but the
                      two photos could not be confirmed as the same pack. The
                      distinction matters: reporting "front_not_provided" for a
                      front that was photographed and read is a false reason,
                      and a reason field that lies is worse than no reason at
                      all - someone debugging it will go looking for a missing
                      image that was never missing.

    Returns a dict. When the front was not read, `status` says so and
    `checked` is empty - this never returns "no contradictions found" for a
    front of pack that was simply never read.
    """
    if front_status != "read":
        return {
            "status": "not_checked",
            "reason": ("pairing_unverified" if front_status == "pairing_unverified"
                       else f"front_{front_status}"),
            "claims_examined": 0,
            "checked": [],
            "unmatched_claims": list(front_claims or []),
        }

    tokens = engine.tokenize(raw_ingredients)
    checked = []
    unmatched = []

    for claim in front_claims or []:
        rule, subject = _match_rule(claim)
        if rule is None:
            unmatched.append(claim)
            continue

        facts = _CHECKS[rule["check"]](result, tokens, subject)
        entry = {
            "claim": claim,
            "rule_id": rule["id"],
            "rule_label": rule["label"],
            "subject": subject or None,
            "contradicted": bool(facts),
            "contradicted_by": facts,
            "confidence": rule["confidence"],
            "verify": rule["verify"],
        }
        if rule["verify"]:
            entry["verify_note"] = rule["note"]
        if rule["check"] == "added_sugar_present":
            adjacent = _adjacent_sugar_notes(result)
            if adjacent:
                entry["adjacent_facts"] = adjacent
        checked.append(entry)

    return {
        "status": "checked",
        "reason": None,
        "claims_examined": len(front_claims or []),
        "checked": checked,
        "unmatched_claims": unmatched,
    }

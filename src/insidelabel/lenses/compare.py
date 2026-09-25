#!/usr/bin/env python3
"""
compare.py - shelf comparison for parents (D-057).

A parent scans 2-4 packs from the same shelf. This module answers one question:
"Which of these is the better pick for my child?"

Rules (keeps D-002, D-004, D-005, D-050 intact):
- Deterministic. Every reason traces to a row in additives.json,
  normalization.json or nova_markers.json. No AI decides the ranking.
- No numeric score is shown. Products are ranked by tiers of concern, and
  the parent sees plain-language reasons, never a number.
- It never says "healthy". Only "fewer concerns" / "better pick of these".
- A pack we could not fully read can never be named the best pick
  (STATE.md ship-blocker #3: unmatched ingredients must not read as clean).
- It is a lens: it re-weights facts for a child's age band. It never changes
  the facts themselves.
- Allergens come first (D-060). A pack that contains, or may contain, something
  on the child's avoid list can never be the best pick, and neither can a pack
  whose allergen status we couldn't confirm (allergens.py, D-071/D-072).
- No legal claim appears in parent text unless its citation is verified.
  (v1.1 fix: the old sweetener line claimed an FSSAI warning requirement that
  FSSAI's own labelling FAQ says no longer applies to sucralose.)

INTEGRATION NOTE: engine.py is not in this project folder, so fact extraction
here reads the JSON tables directly. Once wired into the backend, replace
extract_facts() with a mapping from engine.analyze() flags so the two can
never disagree. Everything below extract_facts() stays the same.
"""

import json
import os
import re
from dataclasses import dataclass, field

from insidelabel.lenses import allergens as allergen_check

DATA_DIR = os.environ.get("INSIDELABEL_DATA", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")))

AGE_BANDS = ("toddler", "kid", "young")  # same bands as prototype.jsx


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


ADDITIVES = {a["ins"]: a for a in _load("additives.json")["additives"] if a["class"] != "note"}
NORM = _load("normalization.json")
NOVA = _load("nova_markers.json")["markers"]
CLAIMS = _load("claim_rules.json")

# Strict added sugars for the "where is sugar in the list" fact. Maltodextrin is
# kept out, matching claim_rules.json (not a sugar under FSSAI/Codex); it is
# reported as its own fact instead.
_ADJ = set(CLAIMS["added_sugar_adjacent"])
SUGARS = [s for s in NORM["sugar_aliases"]["added_sugar"] if s not in _ADJ]

# Name -> INS lookup, so "sodium benzoate" written without a number still matches.
NAME_TO_INS = {}
for ins, a in ADDITIVES.items():
    for part in re.split(r"\s*/\s*|\s*\(|\)", a["name"].lower()):
        part = part.strip()
        if len(part) > 3:
            NAME_TO_INS[part] = ins
for canonical, aliases in NORM["synonyms"].items():
    ins = NAME_TO_INS.get(canonical)
    if ins:
        for al in aliases:
            NAME_TO_INS[al] = ins

ADDITIVE_WORDS = (
    "ins", "colour", "color", "emulsifier", "stabiliser", "stabilizer", "preservative",
    "acidity regulator", "raising agent", "leavening", "sweetener", "flavour enhancer",
    "flavor enhancer", "antioxidant", "thickener", "humectant", "anticaking",
    "firming agent", "glazing agent", "improver", "e",
)

# 3-4 digit INS codes with optional letter / roman suffix: 150d, 339(ii), 1100(iii).
INS_RE = re.compile(r"(?<![\d.])(\d{3,4})([a-d])?(?:\s*\(\s*([ivx]+)\s*\))?(?!\s*(?:[\d.]|%|g\b|mg\b|kcal))")

ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def _word_in(needle, hay):
    return re.search(r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])", hay) is not None


def _base(token):
    """Ingredient name with parentheticals and percentages removed."""
    t = re.sub(r"\([^)]*\)", " ", token.lower())
    t = re.sub(r"\d+(\.\d+)?\s*%", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .,:;")


# ---------------------------------------------------------------- facts

@dataclass
class Fact:
    key: str            # stable id, used to compare products
    tier: str           # "strong" | "moderate" | "info"
    parent_text: str    # what the parent reads
    technical: str      # the tap-through: INS, source, table row
    positive: bool = False


@dataclass
class Product:
    id: str
    name: str
    ingredients: list
    reliable: bool = True          # from app/reliability.py
    allergen_statement: str = None  # prompt.py field, as printed
    confidence: float = 1.0         # prompt.py confidence["ingredients"]
    facts: list = field(default_factory=list)
    unknown_ins: list = field(default_factory=list)

    @property
    def fully_checked(self):
        return self.reliable and not self.unknown_ins


def _find_additives(ingredients):
    found, unknown = {}, []
    for tok in ingredients:
        low = tok.lower()
        looks_additive = any(_word_in(w, low) for w in ADDITIVE_WORDS) or "(" in low
        if looks_additive:
            for m in INS_RE.finditer(low):
                num, letter, roman = m.group(1), m.group(2) or "", m.group(3)
                code = num + letter
                if code in ADDITIVES:
                    found[code] = tok
                elif num in ADDITIVES and not letter:
                    found[num] = tok
                else:
                    unknown.append(code + (f"({roman})" if roman else ""))
        for name, ins in NAME_TO_INS.items():
            if ins not in found and _word_in(name, low):
                found[ins] = tok
    return found, sorted(set(unknown))


def extract_facts(p: Product, age: str):
    """Ingredient facts relevant to a child, with tiers set by the age lens."""
    facts = []
    additives, p.unknown_ins = _find_additives(p.ingredients)

    for ins, _tok in additives.items():
        a = ADDITIVES[ins]
        tags = set(a.get("flags", []))
        name = a["name"]
        tech = f"INS {ins} {name} ({a['class']}, concern: {a['concern']}). {a['why']} Sources: {', '.join(a['sources'])}."

        if "artificial_sweetener" in tags:
            # Fact only. No legal claim: FSSAI's labelling FAQ (June 2022) says
            # sucralose no longer needs a warning statement. Tier is "moderate"
            # until a verified, child-specific citation supports anything stronger.
            facts.append(Fact(f"sweetener:{ins}", "moderate",
                f"Has an artificial sweetener ({name}).", tech))
        elif "southampton_six" in tags:
            facts.append(Fact(f"colour:{ins}", "strong",
                f"Has an artificial food colour ({name}). Europe requires a warning on it "
                f"because it is linked to hyperactivity in some children.", tech))
        elif a["concern"] == "high":
            facts.append(Fact(f"high:{ins}", "strong",
                f"Has {name}, an additive with higher concern (restricted in some countries). Tap to see why.", tech))
        elif "not_for_infants" in tags and age == "toddler":
            facts.append(Fact(f"toddler:{ins}", "strong",
                f"Has {name}, which is not advised for very young children.", tech))
        elif a["concern"] == "moderate" or ("child_sensitivity" in tags):
            facts.append(Fact(f"mod:{ins}", "moderate", f"Has {name} ({a['class'].replace('_', ' ')}).", tech))
        elif "sweetener_natural" in tags:
            facts.append(Fact(f"info:{ins}", "info", f"Sweetened with {name}.", tech))

    # Sugar: position in the list + how many names it hides behind.
    positions, names = [], []
    for i, tok in enumerate(p.ingredients, start=1):
        b = _base(tok)
        hit = next((s for s in sorted(SUGARS, key=len, reverse=True) if _word_in(s, b)), None)
        if hit:
            positions.append(i)
            names.append(hit)
    if positions:
        first = positions[0]
        tier = "strong" if (first <= 2 or (age == "toddler" and first <= 3)) else "moderate"
        text = f"Sugar is the {ORDINAL.get(first, f'{first}th')} ingredient (ingredients are listed from most to least)."
        if len(set(names)) > 1:
            text += f" It appears under {len(set(names))} names: {', '.join(dict.fromkeys(names))}."
        facts.append(Fact(f"sugar_pos:{first}", tier, text,
                          f"Added-sugar aliases from normalization.json at positions {positions}."))
    else:
        facts.append(Fact("no_added_sugar_found", "info", "No added sugar found in the ingredient list.",
                          "No normalization.json added_sugar alias matched.", positive=True))

    # Maltodextrin: its own fact (see claim_rules.json OPEN_QUESTION).
    if any(_word_in(m, _base(t)) for t in p.ingredients for m in _ADJ):
        facts.append(Fact("maltodextrin", "moderate",
            "Has maltodextrin, a processed starch that raises blood sugar quickly.",
            "claim_rules.json added_sugar_adjacent; nova_markers.json nova_maltodextrin."))

    # Caffeine.
    if any(_word_in(w, t.lower()) for t in p.ingredients for w in ("caffeine", "coffee")):
        facts.append(Fact("caffeine", "strong" if age == "toddler" else "moderate",
            "Contains caffeine.", "Ingredient keyword match: caffeine/coffee."))

    # Main ingredient. Only explicit whole wheat gets credit; bare "wheat flour
    # (atta)" is left alone until D-054 is decided.
    if p.ingredients:
        main = _base(p.ingredients[0])
        if "whole wheat" in main or "whole grain" in main:
            facts.append(Fact("main_whole_grain", "info", "Main ingredient is whole wheat.",
                              f"Ingredient 1: {p.ingredients[0]}", positive=True))
        elif "refined" in main or "maida" in p.ingredients[0].lower():
            facts.append(Fact("main_refined", "info", "Main ingredient is refined flour (maida).",
                              f"Ingredient 1: {p.ingredients[0]}"))

    # Ultra-processed markers: counted for tie-breaking, one summary line.
    nova_hits = [m["name"] for m in NOVA
                 if any(_word_in(al, t.lower()) for t in p.ingredients for al in m["aliases"])]
    if nova_hits:
        facts.append(Fact("nova", "info",
            f"{len(nova_hits)} ultra-processed ingredient{'s' if len(nova_hits) > 1 else ''}.",
            "NOVA Group 4 markers (nova_markers.json): " + ", ".join(nova_hits)))

    p.facts = facts
    p._nova = len(nova_hits)
    p._additives = len(additives)
    return p


# -------------------------------------------------------------- ranking

def _rank_key(p: Product):
    strong = sum(f.tier == "strong" for f in p.facts)
    moderate = sum(f.tier == "moderate" for f in p.facts)
    sugar_pos = next((int(f.key.split(":")[1]) for f in p.facts if f.key.startswith("sugar_pos:")), 99)
    # Lower is better; sugar further down the list is better, so negate.
    return (strong, moderate, -sugar_pos, p._nova, p._additives)


def compare(products, age="kid", avoid=(), who=None, strict_may_contain=True):
    """
    avoid: allergen codes from the child's profile (allergens.json).
    who:   the profile nickname, shown to the parent. Stored on the device only.
    strict_may_contain: treat "may contain" as a no (default for allergy families).
    """
    if age not in AGE_BANDS:
        raise ValueError(f"age must be one of {AGE_BANDS}")
    if not 2 <= len(products) <= 4:
        raise ValueError("Compare 2 to 4 packs.")

    who_label = who or AGE_LABEL[age]
    blocked, allergen_unsure, allergen_ok = [], [], {}
    for p in products:
        extract_facts(p, age)
        p.allergens = allergen_check.check(p.ingredients, p.allergen_statement, list(avoid),
                                           confidence=p.confidence, reliable=p.reliable)
        states = {r.state for r in p.allergens.values()}
        if "contains" in states or (strict_may_contain and "may_contain" in states):
            blocked.append(p)
        elif states & {"uncertain", "cannot_confirm"} or ("may_contain" in states):
            allergen_unsure.append(p)
        else:
            allergen_ok[p.id] = True

    candidates = [p for p in products if p.id in allergen_ok]
    checked = sorted([p for p in candidates if p.fully_checked], key=_rank_key)
    unchecked = [p for p in candidates if not p.fully_checked]

    result = {"age": age, "who": who_label, "avoid": list(avoid), "best": None, "tie": [],
              "others": [], "not_checked": unchecked, "blocked": blocked,
              "allergen_unsure": allergen_unsure, "why_best": [], "allergen_lines": []}

    if not checked:
        return result
    best = checked[0]
    ties = [p for p in checked[1:] if _rank_key(p)[:3] == _rank_key(best)[:3]]
    if ties:
        result["tie"] = [best] + ties
        result["others"] = [p for p in checked if p not in result["tie"]]
        return result

    result["best"] = best
    result["others"] = checked[1:]
    result["allergen_lines"] = [best.allergens[c].parent_text(who_label) for c in avoid]
    if not checked[1:]:
        result["why_best"] = [f"The only pack here that passed {who_label}'s avoid list"
                              if blocked else "The only pack here we could fully check"]
        return result
    best_keys = {f.key.split(":")[0] for f in best.facts if f.tier != "info"}
    reasons = {}
    for other in checked[1:]:
        for f in other.facts:
            kind = f.key.split(":")[0]
            if f.tier != "info" and kind not in best_keys:
                reasons.setdefault(kind, f)
    labels = {
        "colour": "No artificial colours",
        "sweetener": "No artificial sweeteners",
        "high": "No high-concern additives",
        "toddler": "Nothing that's not advised for toddlers",
        "maltodextrin": "No maltodextrin",
        "caffeine": "No caffeine",
        "mod": "Fewer additives of concern",
    }
    why = [labels[k] for k in labels if k in reasons]
    bs = next((f for f in best.facts if f.key.startswith("sugar_pos:")), None)
    other_first = [next((int(f.key.split(":")[1]) for f in o.facts if f.key.startswith("sugar_pos:")), 99)
                   for o in checked[1:]]
    if bs is None:
        why.append("No added sugar")
    elif int(bs.key.split(":")[1]) > max(other_first):
        why.append("Less sugar-heavy (sugar is lower down the list)")
    if any(f.key == "main_whole_grain" for f in best.facts) and not all(
            any(f.key == "main_whole_grain" for f in o.facts) for o in checked[1:]):
        why.append("Made mainly from whole wheat")
    if not why:
        why.append("Fewer concerns overall")
    result["why_best"] = why
    return result


# -------------------------------------------------------------- display

AGE_LABEL = {"toddler": "your toddler", "kid": "your child", "young": "your teen"}


def render(result):
    who = result["who"]
    out = []
    if result["best"]:
        b = result["best"]
        out.append(f"BEST PICK OF THESE FOR {who.upper()}: {b.name}")
        if result["allergen_lines"]:
            out.append(f"  {who}'s avoid list:")
            out += [f"    • {t}" for t in result["allergen_lines"]]
        out += [f"  ✓ {w}" for w in result["why_best"]]
        worries = [f for f in b.facts if f.tier != "info"]
        if worries:
            out.append("  Still worth knowing:")
            out += [f"    • {f.parent_text}" for f in worries]
    elif result["tie"]:
        out.append(f"THESE ARE ABOUT THE SAME FOR {who.upper()}:")
        out += [f"  = {p.name}" for p in result["tie"]]
        out.append("  Pick either one. The concerns below are similar.")
        for p in result["tie"]:
            out += [f"    • {p.name}: {f.parent_text}" for f in p.facts if f.tier == "strong"]
    elif result["blocked"] or result["allergen_unsure"]:
        out.append(f"NONE OF THESE PACKS IS A CLEAR PICK FOR {who.upper()}.")
        out.append("  Scan another pack from this shelf and we'll compare again.")
    elif any(p.unknown_ins for p in result["not_checked"]):
        out.append("WE CAN'T COMPARE THESE PACKS YET.")
        out.append("  Some of their additives aren't in our database yet, and we won't guess.")
    else:
        out.append("We couldn't read these packs clearly enough to compare them.")

    for p in result["blocked"]:
        out.append(f"\n{p.name}: not for {who}")
        out += [f"  ✗ {r.parent_text(who)}" for r in p.allergens.values()
                if r.state in ("contains", "may_contain")]

    for p in result["allergen_unsure"]:
        out.append(f"\n{p.name}: check before buying")
        out += [f"  ? {r.parent_text(who)}" for r in p.allergens.values()
                if r.state in ("uncertain", "cannot_confirm", "may_contain")]

    for p in result["others"]:
        concerns = [f for f in p.facts if f.tier in ("strong", "moderate")]
        out.append(f"\n{p.name}: more concerns for {who}")
        out += [f"  • {f.parent_text}" for f in sorted(concerns, key=lambda f: f.tier != "strong")]

    for p in result["not_checked"]:
        why = "the photo wasn't clear" if not p.reliable else \
            f"it has {len(p.unknown_ins)} additive(s) we haven't checked yet"
        out.append(f"\n{p.name}: not compared, because {why}. We won't guess.")
    return "\n".join(out)

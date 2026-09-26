"""
screen.py - what the result screen shows, in the order it shows it (D-060-D-066).

Why this lives on the server and not in the PWA: every sentence a user reads
has to pass the wording lint (D-042, tests/test_wording.py), and the lint can
only see Python and data/*.json. If the headline were assembled in JavaScript,
a forbidden word could ship without a test noticing. So the client renders the
`screen` block as given and adds only UI chrome.

Rules this module keeps:
- It reads engine, allergen, claim and kids-lens output. It never judges
  anything itself (D-004), and it never looks at EU/US status (D-086).
- People first (D-060): one line per profile with an avoid list or a child's
  age band, before anything about the product.
- The headline is one finding, quoted from the row that produced it, with a
  `source` pointing at that row (D-061, D-043). Counts come after it.
- "No concerns found" appears only when the display rule says clean (D-062,
  D-063); a partial read can never produce it.
- `none`/`low` ingredients are grouped as ordinary, not listed as concerns (D-065).
- No numeric score anywhere in this block (D-064).
- Profile names never reach the server (D-074). Text for a profile uses the
  literal placeholder NAME ("{name}"); the device swaps in the nickname. The
  user's own profile ("me") is written as "you"/"your".
"""

from insidelabel.core import engine
from insidelabel.core.tokenize import extract_ins
from insidelabel.lenses import allergens as allergen_checker
from insidelabel.lenses import compare as kids

NAME = "{name}"
MAX_PROFILES = 3                          # D-074
AGES = ("adult",) + kids.AGE_BANDS        # adult = no age lens

# D-063: display names. Band logic is unchanged; only the words differ.
BAND_LABEL = {
    "clean": "No concerns found in the ingredients",
    "mixed": "A few things worth knowing",
    "ultra-processed": "Made with industrial ingredients",
    "incomplete": "We could read only part of the ingredient list",
}
NOVA_NOTE = (
    "Researchers call this \"ultra-processed\" (NOVA group 4): made with "
    "ingredients rarely used in home cooking, such as glucose syrup or modified "
    "starch. It describes how a food is made. It is not advice about whether "
    "it is right for you."
)

# D-036: a retake prompt names the actual problem.
RETAKE = {
    "product_mismatch": "These two photos look like different packs. Photograph the front "
                        "and back of the same pack, or just the back.",
    "back_not_read": "We couldn't find the ingredient list in the photo. Turn the pack over "
                     "and photograph the part that starts with \"Ingredients\".",
    "no_ingredients_extracted": "We couldn't find the ingredient list in the photo. Turn the pack "
                                "over and photograph the part that starts with \"Ingredients\".",
    "no_ingredient_list_found": "We couldn't find the ingredient list in the photo. Turn the pack "
                                "over and photograph the part that starts with \"Ingredients\".",
    "ingredient_list_unreadable": "The ingredient list is too blurred or dark to read. Hold the "
                                  "phone steady, fill the frame with the list and avoid glare.",
}
RETAKE.update({
    # D-103: not a pack at all. Named plainly; no tips about light or focus.
    "back_is_a_screen": "This looks like a photo of a screen. Photograph the pack itself: we only read "
                        "labels from real packs, so a website or app picture can't be used.",
    "not_a_food_pack": "This doesn't look like a food pack. Photograph the ingredient list on the back "
                       "of a packaged food or drink.",
})
# The headline for refusals that aren't about legibility.
HEADLINE = {
    "back_is_a_screen": "This is a photo of a screen, not a pack.",
    "not_a_food_pack": "This doesn't look like a food pack.",
}
NOT_A_PACK = ("back_is_a_screen", "not_a_food_pack")
RETAKE_DEFAULT = "We couldn't read this label. Retake the photo of the ingredient list."
RETAKE_PARTIAL = "Part of the ingredient list was cut off or hard to read. Retake it to check the rest."

_STRONGEST = {"contains": 0, "may_contain": 1, "cannot_confirm": 2, "uncertain": 3, "not_listed": 4}


class ProfileError(ValueError):
    pass


def parse_profiles(items):
    """
    Validate [{ref, age, avoid}] from the client. Only a short ref, an age band
    and allergen codes are accepted, so a nickname has nowhere to go (D-074).
    """
    if not items:
        return []
    if not isinstance(items, list) or len(items) > MAX_PROFILES:
        raise ProfileError(f"profiles must be a list of at most {MAX_PROFILES}.")
    out, seen = [], set()
    for p in items:
        if not isinstance(p, dict) or set(p) - {"ref", "age", "avoid"}:
            raise ProfileError("each profile is {ref, age, avoid} and nothing else.")
        ref, age, avoid = p.get("ref"), p.get("age", "adult"), p.get("avoid") or []
        if not (isinstance(ref, str) and ref.isalnum() and len(ref) <= 8) or ref in seen:
            raise ProfileError("ref must be a distinct id of up to 8 letters or digits.")
        if age not in AGES:
            raise ProfileError(f"age must be one of {', '.join(AGES)}.")
        if not isinstance(avoid, list) or any(c not in allergen_checker.ALLERGENS for c in avoid):
            raise ProfileError("avoid must list allergen codes from GET /allergens.")
        seen.add(ref)
        out.append({"ref": ref, "age": age, "avoid": list(dict.fromkeys(avoid))})
    return out


def _who(profile):
    return "you" if profile["ref"] == "me" else NAME


def _whose(profile):
    return "your" if profile["ref"] == "me" else f"{NAME}'s"


# ------------------------------------------------------------------ people

def _person(profile, ingredients, statement, confidence, reliable):
    """D-064: the glanceable signal for one person, allergens first."""
    who, whose = _who(profile), _whose(profile)
    rows = []
    if profile["avoid"]:
        res = allergen_checker.check(ingredients or [], statement, profile["avoid"],
                                     confidence=confidence, reliable=reliable)
        rows = sorted(res.values(), key=lambda r: _STRONGEST[r.state])

    child_facts = []
    if profile["age"] in kids.AGE_BANDS and reliable and ingredients:
        p = kids.extract_facts(kids.Product("x", "x", ingredients), profile["age"])
        child_facts = [{"tier": f.tier, "text": f.parent_text,
                        "technical": f.technical}
                       for f in p.facts if f.tier == "strong"]

    if rows and rows[0].state != "not_listed":
        status, line = rows[0].state, rows[0].parent_text(who)
    elif rows:
        status = "not_listed"
        if all(r.statement_seen for r in rows):
            line = f"Nothing on {whose} avoid list is listed in the ingredients or the allergen line."
        else:
            line = (f"Nothing on {whose} avoid list is in the ingredients. We didn't see a "
                    f"\"may contain\" line in the photo, so check the pack.")
    elif child_facts:
        status = "worth_knowing"
        n = len(child_facts)
        line = f"{n} thing{'s' if n > 1 else ''} worth knowing for {NAME}."
    elif profile["age"] in kids.AGE_BANDS and reliable and ingredients:
        status, line = "nothing_flagged", f"Nothing extra for {NAME}'s age came up."
    else:
        return None                      # an adult with no avoid list has no line
    return {
        "ref": profile["ref"],
        "status": status,
        "line": line,
        "allergens": [{"code": r.code, "state": r.state, "evidence": r.evidence or None,
                       "text": r.parent_text(who)} for r in rows],
        "child_facts": child_facts,
    }


# ------------------------------------------------------------------ product

def _additive_name(flag):
    ins = extract_ins(flag["matched_as"])
    a = engine._ADDITIVE_BY_INS.get(ins) if ins else None
    return a["name"] if a else flag["matched_as"].partition(" (INS ")[0]


def _findings(verdict):
    """Split engine flags into worth-knowing items and ordinary ones (D-065)."""
    worth, ordinary, nova, seen = [], [], [], set()
    for f in verdict["flags"]:
        if f["matched_as"] in seen:
            continue
        seen.add(f["matched_as"])
        if f["type"] == "nova_marker":
            nova.append(f)
            continue
        item = {"name": _additive_name(f), "label_text": f["ingredient"], "why": f["why"],
                "technical": f"{f['matched_as']}. Sources: {', '.join(f['sources'])}.",
                "concern": f["concern"], "source": {"kind": "additive", "ref": f["matched_as"]}}
        (worth if f["concern"] in ("moderate", "high") else ordinary).append(item)
    worth.sort(key=lambda i: i["concern"] != "high")
    if nova:
        # Table names, not tokens: a token can be a fragment like "flavours (natural".
        names = list(dict.fromkeys(f["matched_as"].removeprefix("NOVA marker: ").lower() for f in nova))
        worth.append({
            "name": "Industrial ingredients",
            "label_text": ", ".join(names),
            "why": NOVA_NOTE,
            "technical": "NOVA group 4 markers: " + "; ".join(f["matched_as"] for f in nova) + ".",
            "concern": "moderate",
            "source": {"kind": "nova", "ref": [f["matched_as"] for f in nova]},
        })
    # Maltodextrin and the other added_sugar_adjacent names are not sugars under
    # the added-sugar definition (claim_rules.json _meta), so they don't count here.
    sugars = [n for n in verdict.get("hidden_sugar_names") or [] if n not in kids._ADJ]
    if len(sugars) > 1:
        worth.append({
            "name": f"Sugar under {len(sugars)} names",
            "label_text": ", ".join(sugars),
            "why": "These are all added sugars. Ingredients are listed from most to least, "
                   "so each name sits lower on the list than their total would.",
            "technical": "normalization.json added_sugar aliases matched: " + ", ".join(sugars) + ".",
            "concern": "moderate",
            "source": {"kind": "hidden_sugar", "ref": sugars},
        })
    return worth, ordinary


def _claim_rows(claim_check):
    """Released claim-check results (D-051), each quoting the label (D-042)."""
    if not claim_check or claim_check.get("status") != "checked":
        return []
    rows = []
    for c in claim_check.get("checked", []):
        by = (c.get("contradicted_by") or [])
        rows.append({
            "claim": c["claim"],
            "contradicted": bool(c.get("contradicted")),
            "text": (f"The front says \"{c['claim']}\". {by[0]['fact']}" if c.get("contradicted") and by
                     else f"The front says \"{c['claim']}\". We found nothing in the ingredient list against it."),
            "source": {"kind": "claim", "ref": c["rule_id"]},
        })
    return rows


def _headline(band, worth, claims, reliability):
    """D-061: one finding, strongest first, with the row it came from."""
    hit = next((c for c in claims if c["contradicted"]), None)
    if hit:
        return {"text": hit["text"], "source": hit["source"]}
    high = next((w for w in worth if w["concern"] == "high"), None)
    if high:
        return {"text": f"Has {high['name']}, an additive with higher concern.", "source": high["source"]}
    sugar = next((w for w in worth if w["source"]["kind"] == "hidden_sugar"), None)
    if sugar:
        return {"text": f"Sugar appears under {len(sugar['source']['ref'])} names: {sugar['label_text']}.",
                "source": sugar["source"]}
    named = next((w for w in worth if w["source"]["kind"] == "additive"), None)
    if named:
        return {"text": f"Has {named['name']}.", "source": named["source"]}
    nova = next((w for w in worth if w["source"]["kind"] == "nova"), None)
    if nova:
        names = nova["label_text"].split(", ")
        shown = " and ".join(names[:2]) if len(names) <= 2 else f"{', '.join(names[:2])} and more"
        return {"text": f"Made with industrial ingredients, such as {shown}.", "source": nova["source"]}
    if worth:
        return {"text": f"Has {worth[0]['name']}.", "source": worth[0]["source"]}
    if band == "incomplete" or not reliability.get("ingredients_complete", True):
        return {"text": BAND_LABEL["incomplete"] + ".", "source": {"kind": "reliability", "ref": "partial"}}
    if band == "clean":
        return {"text": BAND_LABEL["clean"] + ".", "source": {"kind": "none", "ref": None}}
    return {"text": BAND_LABEL.get(band, BAND_LABEL["mixed"]) + ".", "source": {"kind": "band", "ref": band}}


def build(*, verdict, display, claim_check, extracted, reliability, profiles,
          allergen_confidence, allergen_reliable, catalogue=None):
    """The `screen` block of a /scan response. verdict=None means the scan was refused."""
    ingredients = (extracted or {}).get("ingredients") or []
    statement = (extracted or {}).get("allergen_statement")
    people = [p for p in (_person(pr, ingredients, statement, allergen_confidence, allergen_reliable)
                          for pr in profiles) if p]

    if verdict is None:
        error = reliability.get("error")
        return {
            "state": "retake",
            "people": people,
            "headline": {"text": HEADLINE.get(error, "We couldn't read this label clearly."),
                         "source": {"kind": "reliability", "ref": error}},
            "retake": RETAKE.get(error, RETAKE_DEFAULT),
            # D-096/D-103: a pack we couldn't read can go to a reviewer; a photo
            # that isn't a pack can't.
            "can_send": error not in NOT_A_PACK,
        }

    band = display["display_binary"]
    worth, ordinary = _findings(verdict)
    claims = _claim_rows(claim_check)
    # Same unit as `scope` (parsed items, sub-ingredients included): everything
    # not already named under worth knowing, counting each item once.
    named = {f["ingredient"].lower() for f in verdict["flags"]
             if f["type"] == "nova_marker" or f["concern"] in ("moderate", "high")}
    for w in worth:
        if w["source"]["kind"] == "hidden_sugar":
            named |= set(w["source"]["ref"])
    n_ord = max(verdict.get("ingredient_count_parsed", 0) - len(named), 0)
    checked = ("We checked the ingredients and the claims on the front." if claims
               else "We checked the ingredients.")
    out = {
        "state": "result",
        "people": people,                                     # D-060: first
        "headline": _headline(band, worth, claims, reliability),
        "band": {"code": band, "label": BAND_LABEL.get(band, band),
                 "note": NOVA_NOTE if band == "ultra-processed" else None},
        "checked": checked,
        "scope": (f"{verdict.get('ingredient_count_parsed', 0)} ingredients checked against "
                  f"{len(engine._ADDITIVE_BY_INS)} additives and {len(engine.NOVA['markers'])} "
                  f"processing markers in our tables."),
        "claims": claims,
        "worth_knowing": worth,
        "ordinary": {"count": n_ord,
                     "text": (f"{n_ord} other ingredient{'s' if n_ord != 1 else ''} look ordinary."
                              if n_ord else None),
                     "additives": ordinary},
        "ingredients": ingredients,
        "retake": None if reliability.get("ingredients_complete", True) else RETAKE_PARTIAL,
    }
    if catalogue and catalogue.get("source") == "catalogue":
        out["last_verified"] = f"Label last verified on {catalogue['last_verified']}."
        # D-073: a barcode can outlive a recipe. Ask anyone with an avoid list for one back photo.
        if any(p["avoid"] for p in profiles):
            out["recheck"] = "Packs change. Photograph the back of your pack to re-check the avoid list."
    return out

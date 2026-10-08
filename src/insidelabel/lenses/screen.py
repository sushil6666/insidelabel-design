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
- Each additive carries a badge built from its FSSAI fields (D-111): "Not
  permitted in India" only on a sure read, "Worth knowing", or "Permitted in
  India" only when the row records its Appendix A basis.
- Profile names never reach the server (D-074). Text for a profile uses the
  literal placeholder NAME ("{name}"); the device swaps in the nickname. The
  user's own profile ("me") is written as "you"/"your".
"""

import json
import os

from insidelabel.core import engine, pack_kind
from insidelabel.core.tokenize import extract_ins, ins_numbers
from insidelabel.lenses import allergens as allergen_checker
from insidelabel.lenses import compare as kids
from insidelabel.lenses import nutra, nutrition

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
# The sugar card's source line (normalization.json sugar_aliases _note: FSSAI L&D 2020,
# added sugars = mono- and disaccharides added). Never a file name or table key.
SUGAR_SOURCE = ("Source: FSSAI's definition of added sugars (Labelling and Display "
                "Regulations, 2020), as applied in InsideLabel's list of sugar names.")

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
    # D-118: a new pack, and our second reader couldn't confirm the ingredient list.
    "independent_read_failed": "We need one clearer photo of the ingredient list to add this pack. "
                               "Hold it flat and close, without glare.",
    # D-103: not a pack at all. Named plainly; no tips about light or focus.
    "back_is_a_screen": "This looks like a photo of a screen. Photograph the pack itself: we only read "
                        "labels from real packs, so a website or app picture can't be used.",
    "not_a_food_pack": "This doesn't look like a food pack. Photograph the ingredient list on the back "
                       "of a packaged food or drink.",
    # D-172 (Sushil, 2026-10-07, "Set A"): Gemini's guard blocked its answer. The photos aren't
    # the problem, so the line says so; with a barcode a person reads it ("Send it to us" at once).
    "vision_blocked": "Your photos look fine. Send them to us and our team will read the label and add "
                      "this pack.",
})
# D-172: without a barcode there is nothing to send (D-107); another photo may pass.
RETAKE_BLOCKED_NO_BARCODE = ("Your photos look fine, but our reader couldn't read this label. Try one more "
                             "photo, a little closer to the list.")
# The headline for refusals that aren't about legibility.
HEADLINE = {
    "back_is_a_screen": "This is a photo of a screen, not a pack.",
    "not_a_food_pack": "This doesn't look like a food pack.",
    # D-118: we read the label, but a second reader couldn't confirm the list.
    "independent_read_failed": "One clearer photo, please.",
    "vision_blocked": "We couldn't read this pack automatically.",              # D-172
}
NOT_A_PACK = ("back_is_a_screen", "not_a_food_pack")
# When a front was sent too, say which photo is the problem: the front may be a
# perfectly good pack (Sushil's test: a screenshot back with a real Ziggy front).
HEADLINE_BACK = {
    "back_is_a_screen": "The back photo is a photo of a screen, not a pack.",
    "not_a_food_pack": "The back photo isn't a food pack.",
}
RETAKE_BACK = {
    "back_is_a_screen": "The back photo looks like a photo of a screen. Turn the pack over and photograph "
                        "the ingredient list on the pack itself.",
    "not_a_food_pack": "The back photo doesn't show a food pack. Turn the pack over and photograph the "
                       "ingredient list, the part that starts with \"Ingredients\".",
}
RETAKE_DEFAULT = "We couldn't read this label. Retake the photo of the ingredient list."
# D-166: the only list read was a recipe's printed on the pack. It has its own
# "Ingredients" heading, so RETAKE's words could send the user back to it.
RETAKE_RECIPE = ("This looks like a recipe printed on the pack, not its own ingredient list. Look for the "
                 "list that starts with \"Ingredients\" near the nutrition table, usually on the back or a "
                 "side, and photograph that.")
RETAKE_PARTIAL = "Part of the ingredient list was cut off or hard to read. Retake it to check the rest."

# D-170 (Sushil, 2026-10-07, "Accept, no hint line"): a refused or rejected photo is shown
# back to the user with its problem named in a short label; the fix line is the sentence
# above (RETAKE and friends), unchanged. Keyed by what the server already knows: the
# reliability error, the photo check's code (photo_check.MESSAGES, CHECK_MESSAGES,
# barcode.MESSAGES), "partial", "recipe" (D-166) and "screen_unread" (D-130).
_NO_LIST = "No ingredient list in this photo"
_BARCODE_UNCLEAR = "Barcode not clear"
PROBLEM_LABEL = {
    "photo_too_small": "Too small",
    "photo_blank": "Too dark or blank",
    "not_an_image": "Not a photo we can read",
    "ingredient_list_unreadable": "Too blurred or dark to read",
    "partial": "Part of the list is cut off",
    "no_ingredient_list_found": _NO_LIST,
    "back_not_read": _NO_LIST,
    "no_ingredients_extracted": _NO_LIST,
    "recipe": "This is a recipe, not the pack's list",
    "back_is_a_screen": "This is a screen, not a pack",
    "screen_unread": "No list we can read on this screen",
    "not_a_food_pack": "Not a food pack",
    "product_mismatch": "Front and back look like different packs",
    "independent_read_failed": "One clearer photo, please",
    "vision_blocked": "Our reader couldn't read this label",                    # D-172
    "unknown": "We couldn't read this label",
    # A barcode photo (D-104). A code that fails its length or check digit was misread.
    "no_barcode": "No barcode found",
    "several_barcodes": "More than one barcode",
    "case_code": "A carton's barcode",
    "store_code": "A shop's own label",
    "not_a_product": "Not a food pack's barcode",
    "barcode_unsure": _BARCODE_UNCLEAR,
    "length": _BARCODE_UNCLEAR,
    "check_digit": _BARCODE_UNCLEAR,
}


def problem(code, fix):
    """D-170: one photo problem for the app to draw: its code, short label and fix line."""
    if code not in PROBLEM_LABEL:
        code = "unknown"
    return {"code": code, "label": PROBLEM_LABEL[code], "fix": fix}


def _partial_problem(out, reliability):
    """D-170: a partial read's retake card names its problem. Added only then, so a full
    read's screen block is exactly as before."""
    if not reliability.get("ingredients_complete", True):
        out["problem"] = problem("partial", RETAKE_PARTIAL)


_STRONGEST = {"contains": 0, "may_contain": 1, "cannot_confirm": 2, "uncertain": 3, "not_listed": 4}

# D-111: one badge per additive, each a fact from its row in data/additives.json
# (fssai_status + fssai_basis, checked against Appendix A, D-046). Never "safe",
# never "banned", never a risk level; EU/US status never picks one (D-086).
BADGE_TEXT = {
    "not_permitted": "Not permitted in India",
    "worth_knowing": "Worth knowing",
    "permitted": "Permitted in India",
}
_BADGE_ORDER = {"not_permitted": 0, "worth_knowing": 1, "permitted": 2}
# "Not permitted" is the most serious thing the app says about a pack, so it
# needs a sure read; otherwise the number itself may be a misread.
CHECK_NUMBER = ("Check this number on the pack: part of the list was hard to read, "
                "so we can't be sure we read it right.")
ADDITIVE_ALERT = "An additive on this label isn't in FSSAI's permitted list."


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

def _names(codes):
    names = [allergen_checker.ALLERGENS[c]["short"] for c in codes]
    return names[0][0].upper() + names[0][1:] + "".join(", " + n for n in names[1:])


def _day(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[int(m) - 1]} {y}"


def _screen_text(r, who):
    """D-130: an allergen row read from a screen says so."""
    a = allergen_checker.ALLERGENS[r.code]
    whose = "your" if who == "you" else f"{who}'s"
    if r.state == "contains":
        return f"Contains {a['short']}, as listed on this screen. It's on {whose} avoid list."
    if r.state == "may_contain":
        return f"The listing on this screen says it may contain {a['short']}."
    if r.state == "cannot_confirm":
        return (f"We couldn't read the list on this screen clearly enough to check for {a['short']}. "
                f"Check the pack in the shop.")
    return r.parent_text(who)


def _pack_text(state, code, day):
    """D-130 case A: our catalogue's pack lists what the screen doesn't."""
    short = allergen_checker.ALLERGENS[code]["short"]
    said = (f"{short[0].upper() + short[1:]}: listed on the pack we checked on {day}." if state == "contains"
            else f"The pack we checked on {day} says it may contain {short}.")
    return said + " This screen doesn't show it, so the listing may be old."


def _screen_rows(profile, rows, pack):
    """
    D-130: each allergen as [code, state, evidence, text]. The screen's own read,
    except where our catalogue's pack (read from a real one) lists what the
    screen doesn't: a listing can be older than the pack in the shop.
    """
    who = _who(profile)
    packed = {}
    if pack:
        packed = allergen_checker.check(pack["ingredients"] or [], pack["allergen_statement"],
                                        profile["avoid"])
    out = []
    for r in rows:
        p = packed.get(r.code)
        if r.state not in ("contains", "may_contain") and p and p.state in ("contains", "may_contain"):
            out.append((r.code, p.state, p.evidence or None, _pack_text(p.state, r.code, _day(pack["verified_on"]))))
        else:
            out.append((r.code, r.state, r.evidence or None, _screen_text(r, who)))
    return sorted(out, key=lambda x: _STRONGEST[x[1]]), packed


def _screen_person(profile, rows, pack):
    """D-130: one person's allergen line for a result read from a screen."""
    merged, packed = _screen_rows(profile, rows, pack)
    top = merged[0]
    if top[1] != "not_listed":
        status, line = top[1], top[3]
    elif packed and all(p.state == "not_listed" for p in packed.values()):
        # Case B: the screen and our pack agree.
        status = "not_listed"
        line = (f"{_names(profile['avoid'])}: not listed, on this screen and on the pack we checked on "
                f"{_day(pack['verified_on'])}. Check the pack when you buy.")
    else:
        # Case C: the screen only. The caution is part of the line, never a separate note.
        status = "not_listed"
        buying = "you buy" if profile["ref"] == "me" else f"buying for {NAME}"
        line = (f"{_names(profile['avoid'])}: not listed in the ingredients on this screen. Listings can "
                f"differ from the pack in the shop. Check the pack before {buying}.")
    return status, line, [{"code": c, "state": st, "evidence": ev, "text": t} for c, st, ev, t in merged]


# D-188 (Sushil, 2026-10-08): an allergen line sits at the top of the result only when it
# matters: a match (red, D-169) or a line we can't confirm (amber). A person with no match
# gets nothing anywhere on the result (his option B: "i thought it won't show anything, but
# it says not listed"); "For you" keeps one "may contain" reminder. The /scan answer's
# `allergens` block is unchanged (D-060); only how it shows on the result screen moves.
CARD_STATUS = ("contains", "may_contain", "uncertain", "cannot_confirm", "worth_knowing")


def _quote(r, ingredients, statement):
    """Where a listed allergen was read, quoted as printed: an ingredient, or the allergen line."""
    ev = (r.evidence or "").strip()
    if not ev:
        return None, False
    if ev in (ingredients or []):
        return ev, False
    low = (statement or "").lower()
    i = low.find(ev.lower())
    return ((statement[i:i + len(ev)] if i >= 0 else ev).strip(), True)


def _match_text(r, who, ingredients, statement):
    """D-188: one listed allergen, calm and factual: what is listed and where, quoted."""
    short = allergen_checker.ALLERGENS[r.code]["short"]
    quote, in_line = _quote(r, ingredients, statement)
    if r.state == "contains":
        where = " in the allergen line" if in_line else ""
        return f"{short[0].upper() + short[1:]} is listed{where}" + (f": \"{quote}\"." if quote else ".")
    if r.state == "may_contain":
        return f"The pack says it may contain {short}" + (f": \"{quote}\"." if quote else ".")
    return r.parent_text(who)                # uncertain: its own words already ask the brand


def _cannot_confirm_text(codes, complete):
    """D-188: one line for a person whose avoid list we couldn't check (D-060's cannot_confirm)."""
    names = _names(codes)
    names = names[0].lower() + names[1:]
    if not complete:
        return f"Part of the list couldn't be read, so we can't confirm {names}. Check the pack."
    return f"The list wasn't clear enough to confirm {names}. Check the pack."


def _weaker_text(r):
    """
    D-188 follow-up (Sushil, 2026-10-08): an allergen brands don't have to declare (sesame,
    data/allergens.json `fssai_mandatory: false` and its `note`) that isn't listed keeps the
    words D-071's line always had, in "For you". Never "safe" or "free from".
    """
    return f"Brands don't have to declare {allergen_checker.ALLERGENS[r.code]['short']}, so this check is weaker."


# D-188: said once in "For you" when an avoid-list allergen isn't listed and no allergen line was
# read: the one reminder left of the "not listed" lines. A photo scan says "in the photo"; a
# barcode-only hit was read from the pack we checked (Sushil, 2026-10-08).
MAY_CONTAIN_NOTE = {
    "photo": "We didn't see a \"may contain\" line in the photo, so check the pack for one.",
    "pack": "We didn't see a \"may contain\" line on the pack we checked, so check the pack for one.",
}


def _person(profile, ingredients, statement, confidence, reliable, screen=False, pack=None, baby=(),
            complete=True, where="photo"):
    """
    D-064: the glanceable signal for one person, allergens first. baby: baby_lines().
    D-188: `line` is the card at the top of the result; build() keeps a card only for a match
    or a line we can't confirm. `quiet` (when set) is a child's age line for "For you";
    `note` is the "may contain" reminder when something on the avoid list isn't listed.
    """
    who, whose = _who(profile), _whose(profile)
    rows = []
    if profile["avoid"]:
        res = allergen_checker.check(ingredients or [], statement, profile["avoid"],
                                     confidence=confidence, reliable=reliable)
        rows = sorted(res.values(), key=lambda r: _STRONGEST[r.state])
    if screen and rows:
        status, line, allergens = _screen_person(profile, rows, pack)
        out = {"ref": profile["ref"], "status": status, "line": line, "allergens": allergens,
               "child_facts": [f for f in _child_facts(profile, ingredients, reliable, baby)]}
        return out                       # D-130: the from_screen card says where it was read

    child_facts = _child_facts(profile, ingredients, reliable, baby)
    quiet = None
    texts = {}
    if rows and rows[0].state == "cannot_confirm":
        status = "cannot_confirm"
        line = _cannot_confirm_text(profile["avoid"], complete)
        texts = {r.code: line for r in rows}
    elif rows and rows[0].state != "not_listed":
        texts = {r.code: (_match_text(r, who, ingredients, statement) if r.state != "not_listed"
                          else r.parent_text(who, where)) for r in rows}
        status, line = rows[0].state, texts[rows[0].code]
    elif rows:
        status, line = "not_listed", None
    else:
        status = line = None
    if status in (None, "not_listed"):
        if child_facts:
            status = "worth_knowing"
            n = len(child_facts)
            line = f"{n} thing{'s' if n > 1 else ''} worth knowing for {NAME}."
        elif status is None and profile["age"] in kids.AGE_BANDS and reliable and ingredients:
            status, line = "nothing_flagged", f"Nothing extra for {NAME}'s age came up."
            quiet = line
        elif status is None:
            return None                  # an adult with no avoid list has no line
    out = {
        "ref": profile["ref"],
        "status": status,
        "line": line,
        "allergens": [{"code": r.code, "state": r.state, "evidence": r.evidence or None,
                       "text": texts.get(r.code) or r.parent_text(who, where)} for r in rows],
        "child_facts": child_facts,
    }
    weak = [_weaker_text(r) for r in rows
            if r.state == "not_listed" and not allergen_checker.ALLERGENS[r.code].get("fssai_mandatory", True)]
    quiet = [x for x in [quiet, *weak] if x]
    if quiet:
        out["quiet"] = quiet
    if any(r.state == "not_listed" and not r.statement_seen for r in rows):
        out["note"] = MAY_CONTAIN_NOTE[where]
    return out


def split_people(people):
    """
    D-188: the cards at the top of the result (a match, a line we can't confirm, or a child's
    age line, amber, with its facts), and "For you": "Nothing extra for {name}'s age came up.",
    the weaker-check line for sesame when it isn't listed, and the one "may contain" reminder.
    A person with nothing of these is in neither.
    """
    cards, quiet = [], []
    for p in people:
        card = p["status"] in CARD_STATUS
        lines = p.get("quiet") or []
        if card:
            cards.append({k: v for k, v in p.items() if k not in ("quiet", "note")})
        if lines:
            quiet.append({"ref": p["ref"], "status": "nothing_flagged" if p["status"] == "nothing_flagged"
                          else "not_listed", "lines": lines})
    note = next((p["note"] for p in people if p.get("note")), None)
    return cards, quiet, note


def _child_facts(profile, ingredients, reliable, baby=()):
    out = []
    if profile["age"] in kids.AGE_BANDS and reliable and ingredients:
        p = kids.extract_facts(kids.Product("x", "x", ingredients), profile["age"])
        out = [{"tier": f.tier, "text": f.parent_text, "technical": f.technical}
               for f in p.facts if f.tier == "strong"]
    return out + (list(baby) if profile["age"] == "baby" else [])


# D-140: a baby profile (under 2) on an ordinary food or a supplement: only the lines
# data/baby_lines.json quotes from its sources, each when its trigger is on this pack.
# Never on an infant food, a special medical food or a pack that isn't food: an infant
# result gives no feeding advice at all until the lawyer answers.
with open(os.path.join(engine.DATA_DIR, "baby_lines.json"), encoding="utf-8") as _fh:
    BABY = json.load(_fh)


def _baby_cite(row):
    src = BABY["_meta"]["sources"][row["source"]]
    return {"title": src["title"], "url": src["url"], "page": row["page"],
            "cite": f"{src['title']}, {row['page']}"}


def _baby_hits(row, ingredients):
    names, ins, exclude = row.get("names", []), set(row.get("ins", [])), row.get("exclude", [])
    for entry in ingredients:
        low = entry.lower()
        if any(kids._word_in(x, low) for x in exclude):
            continue
        if any(kids._word_in(n, low) for n in names) or ins & set(ins_numbers(entry)):
            return True
    return False


def _hfss(panel):
    """A checked nutrition table whose salt or added sugar is over Table 15.1 (D-133's own rows)."""
    if not panel or panel.get("status") not in nutrition.SHOWN or not panel.get("values"):
        return False
    rows, _ = _nutrition_rows(panel)
    return any(r["over"] and r["key"] in ("salt", "added_sugars") for r in rows)


def baby_lines(kind_code, ingredients, reliable, panel=None):
    """The `child_facts` items a baby profile gets on this pack (D-140), in the table's order."""
    if kind_code not in ("food", "supplement"):
        return []
    on = set()
    for row in BABY["lines"]:
        t = row["trigger"]
        if t == "supplement":
            hit = kind_code == "supplement"
        elif kind_code != "food":
            hit = False
        elif t == "hfss":
            hit = _hfss(panel)
        elif not (reliable and ingredients):
            hit = False
        elif t == "added_sugar":
            hit = bool(kids.sugar_positions(ingredients))
        else:
            hit = _baby_hits(row, ingredients)
        if hit:
            on.add(row["id"])
    return [{"tier": "strong", "text": row["text"], "technical": _baby_cite(row)["cite"],
             "sources": [_baby_cite(row)], "source": {"kind": "baby_line", "ref": row["id"]}}
            for row in BABY["lines"] if row["id"] in on]


# D-140: the `toddler` band was "1 to 3 years" and is now "2 to 3 years". A phone's
# toddler profiles made before that are asked once, on a result, whether the child is
# under 2; the app keeps the answer on the phone and never asks that profile again.
# Never on a scan that already had D-146's digit check (at most one check per scan).
BAND_QUESTION = {
    "text": f"Is {NAME} under 2?",
    "why": "We now show a few extra lines from ICMR-NIN and WHO for children under 2.",
    "yes": "Yes, under 2",
    "no": "No, 2 or older",
    "done_yes": f"Thanks. {NAME} is now in the under 2 band. You'll see it from your next scan.",
    "done_no": f"Thanks. {NAME} stays in the 2 to 3 years band.",
}


def _band_question(profiles, barcode_answer):
    refs = [p["ref"] for p in profiles if p["age"] == "toddler"]
    if not refs or barcode_answer:
        return None
    return {"refs": refs, **BAND_QUESTION}


# ------------------------------------------------------------------ product

def _additive_name(flag):
    ins = extract_ins(flag["matched_as"])
    a = engine._ADDITIVE_BY_INS.get(ins) if ins else None
    return a["name"] if a else flag["matched_as"].partition(" (INS ")[0]


def _badge(row, concern, sure):
    """D-111: the badge for one additive, or None when its row can't back one."""
    status = (row or {}).get("fssai_status")
    if status == "not_permitted":
        if sure:
            return {"kind": "not_permitted", "text": BADGE_TEXT["not_permitted"]}
        return {"kind": "worth_knowing", "text": BADGE_TEXT["worth_knowing"], "note": CHECK_NUMBER}
    if concern in ("moderate", "high"):
        return {"kind": "worth_knowing", "text": BADGE_TEXT["worth_knowing"]}
    if status in ("permitted", "permitted_with_limits") and row.get("fssai_basis") and row.get("verified_on"):
        return {"kind": "permitted", "text": BADGE_TEXT["permitted"]}
    return None


def _findings(verdict, sure=True):
    """Split engine flags into worth-knowing items and ordinary ones (D-065).
    `sure`: a complete read at allergen-gate confidence (D-111)."""
    worth, ordinary, nova, seen = [], [], [], set()
    for f in verdict["flags"]:
        if f["matched_as"] in seen:
            continue
        seen.add(f["matched_as"])
        if f["type"] == "nova_marker":
            nova.append(f)
            continue
        ins = extract_ins(f["matched_as"])
        item = {"name": _additive_name(f), "label_text": f["ingredient"], "why": f["why"],
                "technical": f"{f['matched_as']}. Sources: {engine.source_names(f['sources'])}.",
                "concern": f["concern"], "source": {"kind": "additive", "ref": f["matched_as"]},
                "ins": ins,
                "badge": _badge(engine._ADDITIVE_BY_INS.get(ins) if ins else None, f["concern"], sure)}
        (worth if f["concern"] in ("moderate", "high") else ordinary).append(item)
    worth.sort(key=lambda i: i["concern"] != "high")
    if nova:
        # D-115: the pack's words (label_term), never the table row's name, which
        # is a category and would show words the label doesn't say. The row name
        # stays in "technical", marked as ours.
        names = list(dict.fromkeys(f.get("label_term") or f["ingredient"] for f in nova))
        worth.append({
            "name": "Industrial ingredients",
            "label_text": ", ".join(names),
            "why": NOVA_NOTE,
            "technical": "NOVA group 4 markers: "
                         + "; ".join(f["matched_as"].removeprefix("NOVA marker: ") for f in nova) + ".",
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
            # A plain source line: the card already quotes the label's names above it.
            "technical": SUGAR_SOURCE,
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


def _ordinal(n):
    return kids.ORDINAL.get(n, f"{n}th")


def _class_words(ins):
    """'a preservative', 'an acidity regulator': the row's class in plain words."""
    a = engine._ADDITIVE_BY_INS.get(ins) or {}
    words = (a.get("class") or "additive").replace("_", " ")
    return ("an " if words[0] in "aeiou" else "a ") + words


def _sugar_sentence(found):
    """D-123: where sugar sits, then its other names. `found` from kids.sugar_positions()."""
    first_pos, first = found[0]
    lead = (f"Sugar is the {_ordinal(first_pos)} ingredient" if first == "sugar"
            else f"Added sugar comes {_ordinal(first_pos)} in the list, as {first}")
    others = list(dict.fromkeys(n for _, n in found if n != first))
    if not others:
        return lead + "."
    if len(others) == 1:
        return f"{lead}, and appears again as {others[0]}."
    return f"{lead}, and appears again under {len(others)} other names."


def _headline(band, worth, claims, reliability, sugar_found=()):
    """D-061: one finding, strongest first, with the row it came from."""
    hit = next((c for c in claims if c["contradicted"]), None)
    if hit:
        return {"text": hit["text"], "source": hit["source"]}
    high = next((w for w in worth if w["concern"] == "high"), None)
    if high:
        return {"text": f"Has {high['name']}, an additive with higher concern.", "source": high["source"]}
    sugar = next((w for w in worth if w["source"]["kind"] == "hidden_sugar"), None)
    if sugar:
        # D-123: where sugar sits says more than a count of its names (Sushil's testers).
        text = (_sugar_sentence(sugar_found) if sugar_found else
                f"Sugar appears under {len(sugar['source']['ref'])} names: {sugar['label_text']}.")
        return {"text": text, "source": sugar["source"]}
    named = next((w for w in worth if w["source"]["kind"] == "additive"), None)
    if named:
        return {"text": f"Has {named['name']}, {_class_words(named['ins'])}.", "source": named["source"]}
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


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _summary(ingredients, sugar_found, worth, adds, complete):
    """
    D-123: the same three answers on every result, in the same order, so two packs
    can be compared at a glance: where sugar sits, how the food is made, and which
    additives are worth knowing. Every answer is a rule's output (D-004), quoted in
    the pack's words where it names ingredients (D-115). `tone` is "worth" or "calm";
    no score (D-064). A partial read never says "none found" (D-062).
    """
    unsure = "Part of the list couldn't be read, so this may be incomplete."
    rows = []

    # Sugar: kids.sugar_positions(), the one place that finds it.
    if sugar_found:
        pos, first = sugar_found[0]
        names = list(dict.fromkeys(n for _, n in sugar_found))
        chip = f"{_ordinal(pos)} of {len(ingredients)}" if complete else _ordinal(pos)
        if len(names) == 1:
            text = f"{first[0].upper() + first[1:]} is listed {_ordinal(pos)}. Ingredients are listed from most to least."
        else:
            later = [f"{n} ({_ordinal(p)})" for n in names[1:]
                     for p in [next(q for q, m in sugar_found if m == n)]]
            text = f"Also listed as {_join(later)}. All are added sugar."
        rows.append({"key": "sugar", "label": "Sugar", "chip": chip,
                     "tone": "worth" if pos <= 3 or len(names) > 1 else "calm", "text": text,
                     "names": len(names), "source": {"kind": "sugar_position", "ref": [p for p, _ in sugar_found]}})
    else:
        rows.append({"key": "sugar", "label": "Sugar", "chip": "None found" if complete else "Not sure",
                     "tone": "calm", "text": ("We found no added sugar names in the ingredient list."
                                              if complete else unsure),
                     "names": 0, "source": {"kind": "sugar_position", "ref": []}})

    # How it's made: the NOVA markers, in the label's words (D-115).
    nova = next((w for w in worth if w["source"]["kind"] == "nova"), None)
    if nova:
        # Sugar syrups are markers too, but the sugar row already names them: lead with the rest.
        sugars = set(kids.SUGARS)
        names = sorted(nova["label_text"].split(", "), key=lambda n: n.lower() in sugars)
        shown = names[:3] + ([f"{len(names) - 3} more"] if len(names) > 3 else [])
        text = _join(shown)
        rows.append({"key": "processing", "label": "How it's made", "chip": "Industrial", "tone": "worth",
                     "text": text[0].upper() + text[1:] + ".", "source": nova["source"]})
    else:
        rows.append({"key": "processing", "label": "How it's made",
                     "chip": "None found" if complete else "Not sure", "tone": "calm",
                     "text": (f"None of the {len(engine.NOVA['markers'])} industrial ingredients we look for, "
                              "such as glucose syrup or emulsifiers." if complete else unsure),
                     "source": {"kind": "nova", "ref": []}})

    # Additives: the D-111 cards, counted; the ones worth knowing named.
    flagged = [i for i in adds if (i["badge"] or {}).get("kind") in ("worth_knowing", "not_permitted")]
    rest = [i for i in adds if i not in flagged]
    def named(i):
        return f"{i['name']} ({(engine._ADDITIVE_BY_INS.get(i['ins']) or {}).get('class', 'additive').replace('_', ' ')} {i['ins']})"
    if not adds:
        rows.append({"key": "additives", "label": "Additives", "chip": "None found" if complete else "Not sure",
                     "tone": "calm", "text": (f"None of the {len(engine._ADDITIVE_BY_INS)} additives in our "
                                              "tables is in the list." if complete else unsure),
                     "source": {"kind": "additives", "ref": []}})
    else:
        parts = []
        if flagged:
            blocked = [i for i in flagged if i["badge"]["kind"] == "not_permitted"]
            if blocked:
                parts.append(f"{_join(named(i) for i in blocked)} isn't in FSSAI's permitted list.")
            others = [i for i in flagged if i not in blocked]
            if others:
                parts.append(f"{_join(named(i) for i in others)} {'is' if len(others) == 1 else 'are'} worth knowing.")
        each = rest and all((i["badge"] or {}).get("kind") == "permitted" for i in rest)
        if rest and flagged:
            parts.append(("The other one is permitted in India." if len(rest) == 1 else
                          f"The other {len(rest)} are permitted in India.") if each
                         else f"{len(rest)} more, with nothing flagged.")
        elif rest:
            parts.append((f"{_join(named(i) for i in rest)}. " if len(rest) <= 2 else "")
                         + ("Permitted in India." if len(rest) == 1 and each else
                            f"All {len(rest)} are permitted in India." if each else "Nothing flagged."))
        chip = f"{len(adds)} · {len(flagged)} to know" if flagged else str(len(adds))
        rows.append({"key": "additives", "label": "Additives", "chip": chip,
                     "tone": "worth" if flagged else "calm", "text": " ".join(parts),
                     "source": {"kind": "additives", "ref": [i["ins"] for i in adds]}})
    return rows


# D-125: "Worth a look" rows, one per additive marked worth knowing. The body is
# data/additive_research.json when a person has read the sources and reviewed it;
# until then, the row's own reason from additives.json.
with open(os.path.join(engine.DATA_DIR, "additive_research.json"), encoding="utf-8") as _fh:
    RESEARCH = json.load(_fh)["rows"]


# D-132: "Ingredients worth knowing", from data/ingredient_notes.json and matched
# by engine.ingredient_notes() on the list as printed. Information only: no score,
# band or headline changes. A row is shown only once a person reviewed it
# (reviewed_by), the D-125 discipline. Tiles are the rows the review marked as
# worth a look (palm oil, hydrogenated fat, maida in the first 3...); the rest are
# plain lines under one closed heading.
NOTES = {r["id"]: r for r in engine.NOTES}
NOTES_TITLE = "More about the ingredients"
NOTE_MORE = "Tap to see what the sources say"
SUGAR_MORE_TITLE = "What the sources say about added sugar"
# The review called hydrogenated fat the strongest of the list, so it leads.
_NOTE_FIRST = ("hydrogenated_fat",)


def _note_shown(row):
    return bool(row and row.get("reviewed_by"))


def _note_sources(row):
    # "cite" is the link text: the document and the page, so the app composes nothing.
    return [{"title": s["title"], "url": s["url"], "page": s.get("page") or None,
             "cite": s["title"] + (f", {s['page']}" if s.get("page") else "")} for s in row["sources"]]


def _notes(ingredients, profiles, complete):
    child = any(p["age"] in kids.AGE_BANDS for p in profiles)
    tiles, lines = [], []
    for hit in engine.ingredient_notes(ingredients):
        row = NOTES[hit["id"]]
        if not _note_shown(row) or (row.get("children_only") and not child):
            continue
        pos = hit["positions"][0]
        rule = row["position_rule"]
        tile = rule == "tile" or (rule == "tile_if_top3" and pos <= 3)
        where = f"Listed {_ordinal(pos)}" + (f" of {len(ingredients)}" if complete else "")
        item = {"id": row["id"], "title": row["title"], "tile": tile, "tone": "worth" if tile else "calm",
                "position": pos, "where": where + ".", "label_line": hit["entries"][0],
                "body": list(row["summary"]), "sources": _note_sources(row),
                "children_only": bool(row.get("children_only")),
                "source": {"kind": "ingredient_note", "ref": row["id"]}}
        if tile:
            item["heading"] = f"Worth a look: {row['title']}"
            item["more"] = f"{where}. {NOTE_MORE}"
            tiles.append(item)
        else:
            lines.append(item)
    if not (tiles or lines):
        return None
    tiles.sort(key=lambda i: (i["id"] not in _NOTE_FIRST, i["position"]))
    lines.sort(key=lambda i: i["position"])
    return {"title": NOTES_TITLE, "tiles": tiles, "lines": lines}


# D-133: the nutrition table beside ICMR-NIN's thresholds (Table 15.1), its daily
# amounts and WHO's shares of daily energy. The words are here, under the lint;
# the figures are data/nutrition_thresholds.json; which numbers can be shown at
# all is lenses/nutrition.py. Information only: no score, band or headline moves,
# except the D-123 rule that "No concerns found" never sits over a tile.
NUT = nutrition.THRESHOLDS
NUTRITION_TITLE = "Nutrition table"
NUTRITION_MISSING = ("We didn't find a nutrition table in the photo. If the pack has one, add a photo of it "
                     "and we'll read it too.")
NUTRITION_UNCLEAR = "We couldn't read the nutrition table clearly."
NUTRITION_PARTIAL = "We couldn't read the nutrition table clearly, so some of its numbers aren't shown."
NUTRITION_UNVERIFIED = ("We couldn't check the nutrition table against a second reading of the photo, "
                        "so its numbers aren't shown.")
NUTRITION_ASK = "Add a photo of the nutrition table"
# D-168 (Sushil, 2026-10-07): a published pack without a nutrition table offers one photo of
# it, at the end of the result. Only the table is read; the ingredients stay as checked.
TABLE_OFFER = {
    "title": "Add the nutrition table?",
    "text": ("We have this pack's ingredients but not its nutrition table. One photo of the table lets our "
             "team add it, so everyone who scans this pack sees its sugar, salt and fat beside ICMR-NIN's "
             "guide."),
    "button": "Photograph the nutrition table",
    "photo": {"title": "Photograph the nutrition table",
              "lead": "Fill the frame with the table. We read only the table; the ingredients stay as we "
                      "checked them.",
              "barcode": "If the barcode is on the same side, keep it in the photo.",
              "button": "Send the table"},
}
TABLE_ANSWER = {
    "added": "Thanks. Our team checks the table, then it shows for everyone who scans this pack.",
    "no_table": "We couldn't find a nutrition table in that photo, so nothing was added.",
    "unclear": "We couldn't read every number on that table clearly, so nothing was added.",
    "different_barcode": "That photo shows a different barcode, so nothing was added.",
}
# D-169: the kind of message each answer is, so the app draws it with that kind's symbol
# and colour without reading the words: "done" for the thanks, "problem" for a photo to retake.
TABLE_ANSWER_KIND = {"added": "done", "no_table": "problem", "unclear": "problem", "different_barcode": "problem"}
NUTRITION_CHECKED = "As printed on the pack, each number checked against a second reading of the photo."
NUTRITION_ADULTS = "The daily amounts are for adults."
MAX_PARTS = 3                            # D-119: the list and the table share the three back photos
_FRACTIONS = ((0.1, "a tenth"), (0.2, "a fifth"), (0.25, "a quarter"), (1 / 3, "a third"), (0.4, "two fifths"),
              (0.5, "half"), (0.6, "three fifths"), (2 / 3, "two thirds"), (0.75, "three quarters"))


def _fmt(x, places=2):
    """20.26 -> '20.26', 44.0 -> '44', 0.030 -> '0.03'."""
    return f"{round(x, places):.{places}f}".rstrip("0").rstrip(".")


def _share(x):
    """What share of a daily amount one serving is, in words: 'about a fifth of'."""
    if x > 1.05:
        return "more than"
    if x >= 0.95:
        return "about as much as"
    near = min(_FRACTIONS, key=lambda f: abs(f[0] - x))
    if abs(near[0] - x) <= 0.025:
        return f"about {near[1]} of"
    pct = round(x * 100)
    return f"about {pct}% of" if pct >= 1 else "less than 1% of"


def _amount_words(v, unit):
    words = {"max": "not more than ", "lt": "less than "}.get(v.get("bound"), "")
    return f"{words}{v['printed']} {unit}"


def _nutrition_rows(panel):
    vals, u = panel["values"], panel["basis"].split(" ")[1]
    t = NUT["per_100"][panel["form"]]
    per = f"per 100 {u}"
    rows = []

    # D-177: `bar` draws the amount beside the threshold its sentence names (value, line, unit, per
    # 100 g or ml): numbers only, so the picture says nothing the words don't. None where the
    # sentence names a share of energy rather than an amount, or a printed "less than" bound.
    # D-185: `amount` and `why` let a row lead with its label and amount and follow with the rest of
    # its sentence, so the value isn't said twice. Both are cut from `text`, which is unchanged: no new
    # words. `why` is None where the sentence doesn't start with the label and amount.
    def row(key, label, text, over, bar=None, amount=None):
        head = f"{label}: {amount} {per}"
        rest = text[len(head):].lstrip(",. ") if amount and text.startswith(head) else ""
        rows.append({"key": key, "label": label, "text": text, "tone": "worth" if over else "calm", "over": over,
                     "bar": bar, "amount": amount if rest else None, "why": rest[:1].upper() + rest[1:] or None})

    def bar(value, line, unit, bound=None):
        return None if bound is not None else {"value": round(value, 2), "line": line, "unit": unit}

    if "energy" in vals:
        e = vals["energy"]
        row("energy", "Energy", f"Energy: {_amount_words(e, 'kcal')} {per}. ICMR-NIN counts more than "
                                f"{_fmt(t['energy_kcal'])} kcal {per} as high.",
            e["bound"] is None and e["value"] > t["energy_kcal"], bar(e["value"], t["energy_kcal"], "kcal", e["bound"]),
            _amount_words(e, "kcal"))
    if "added_sugars" in vals:
        a = vals["added_sugars"]
        row("added_sugars", "Added sugar", f"Added sugar: {_amount_words(a, 'g')} {per}. ICMR-NIN counts more than "
                                           f"{_fmt(t['added_sugar_g'])} g {per} as high.",
            a["bound"] is None and a["value"] > t["added_sugar_g"], bar(a["value"], t["added_sugar_g"], "g", a["bound"]),
            _amount_words(a, "g"))
    elif "total_sugars" in vals:
        row("total_sugars", "Total sugars",
            f"Total sugars: {_amount_words(vals['total_sugars'], 'g')} {per}. The table doesn't show added sugar on "
            f"its own line, so ICMR-NIN's added-sugar threshold isn't applied.", False,
            amount=_amount_words(vals["total_sugars"], "g"))
    salt_mg = None
    if "sodium" in vals:
        s = vals["sodium"]
        salt_mg = s["value"] * nutrition.SALT_PER_SODIUM
        row("salt", "Salt", f"Salt: about {_fmt(salt_mg, 0)} mg {per}, from {_amount_words(s, 'mg')} of sodium "
                            f"(salt is {_fmt(nutrition.SALT_PER_SODIUM)} times the sodium). ICMR-NIN counts more "
                            f"than {_fmt(t['salt_mg'])} mg of salt {per} as high.",
            s["bound"] is None and salt_mg > t["salt_mg"], bar(salt_mg, t["salt_mg"], "mg", s["bound"]),
            f"about {_fmt(salt_mg, 0)} mg")
    elif "salt" in vals:
        s = vals["salt"]
        salt_mg = s["value"] * 1000
        row("salt", "Salt", f"Salt: {_amount_words(s, 'g')} {per}. ICMR-NIN counts more than "
                            f"{_fmt(t['salt_mg'])} mg of salt {per} as high.",
            s["bound"] is None and salt_mg > t["salt_mg"], bar(salt_mg, t["salt_mg"], "mg", s["bound"]),
            _amount_words(s, "g"))
    who = NUT["who_energy_share"]
    kcal = (vals.get("energy") or {}).get("value")
    if "saturated_fat" in vals:
        f = vals["saturated_fat"]
        pct = f["value"] * nutrition.FAT_KCAL / kcal * 100 if kcal else None
        share = f", about {_fmt(pct, 0)}% of the food's energy" if pct is not None else ""
        row("saturated_fat", "Saturated fat",
            f"Saturated fat: {_amount_words(f, 'g')} {per}{share}. WHO advises no more than "
            f"{_fmt(who['saturated_fat_pct'])}% of daily energy from saturated fat.",
            pct is not None and pct > who["saturated_fat_pct"], amount=_amount_words(f, "g"))
    if "trans_fat" in vals:
        f = vals["trans_fat"]
        row("trans_fat", "Trans fat", f"Trans fat: {_amount_words(f, 'g')} {per}. WHO advises no more than "
                                      f"{_fmt(who['trans_fat_pct'])}% of daily energy from trans fat.",
            f["value"] > 0, amount=_amount_words(f, "g"))
    return rows, salt_mg


def _nutrition_servings(panel, salt_mg):
    """Adults' daily amounts, one serving at a time: added sugar (ICMR-NIN) and salt (ICMR-NIN, WHO)."""
    s = panel.get("serving")
    if not s:
        return []
    size, vals, out = f"{_fmt(s['value'])} {s['unit']}", panel["values"], []
    a = vals.get("added_sugars")
    if a and a["bound"] is None:
        grams = a["value"] * s["value"] / 100
        day = NUT["daily"]["added_sugar_g"]["value"]
        out.append({"key": "added_sugars", "text": f"One serving ({size}) has {_fmt(grams, 1)} g added sugar, "
                                                   f"{_share(grams / day)} the {_fmt(day)} g a day ICMR-NIN counts as high."})
    if salt_mg is not None and not (vals.get("sodium") or vals.get("salt") or {}).get("bound"):
        grams = salt_mg * s["value"] / 100 / 1000
        day = NUT["daily"]["salt_g"]["value"]
        out.append({"key": "salt", "text": f"One serving ({size}) has {_fmt(grams, 2)} g salt, "
                                           f"{_share(grams / day)} the {_fmt(day)} g a day ICMR-NIN counts as high."})
    return out


def _nutrition_sources():
    srcs = [NUT["per_100"]["_source"], *NUT["daily"]["added_sugar_g"]["sources"],
            *NUT["daily"]["salt_g"]["sources"], NUT["who_energy_share"]["_source"], nutrition.PANEL["_meta"]["source"]]
    out, seen = [], set()
    for x in srcs:
        cite = x["title"] + (f", {x['page']}" if x.get("page") else "")
        if cite not in seen:
            seen.add(cite)
            out.append({"title": x["title"], "url": x["url"], "page": x.get("page") or None, "cite": cite})
    return out


def _nutrition(panel, parts_sent=1, catalogue=None):
    """The `nutrition` block, or None for a scan whose answer predates D-133."""
    if not panel or panel.get("status") in (None, "not_read"):
        return None
    status = panel["status"]
    # A new photo helps only with a photo we took: not a catalogue pack, not a full set of parts.
    can_ask = not catalogue and parts_sent < MAX_PARTS
    if status in ("missing", "unclear", "unverified"):
        text = {"missing": NUTRITION_MISSING, "unclear": NUTRITION_UNCLEAR, "unverified": NUTRITION_UNVERIFIED}[status]
        ask = can_ask and status != "unverified"
        return {"title": NUTRITION_TITLE, "state": status, "text": text, "rows": [], "servings": [], "tiles": [],
                "ask_photo": ask, "ask": NUTRITION_ASK if ask else None}
    rows, salt_mg = _nutrition_rows(panel)
    servings = _nutrition_servings(panel, salt_mg)
    shown = {r["key"] for r in rows} | ({"sodium"} if any(r["key"] == "salt" for r in rows) else set())
    also = [f"{nutrition.LABEL[k]} {_amount_words(v, v['unit'])}" for k, v in panel["values"].items()
            if k not in shown and k not in ("salt",)]
    tiles = []
    trans = panel["values"].get("trans_fat")
    if trans and trans["value"] > 0:
        tt = NUT["trans_fat_tile"]
        amount = f"{_amount_words(trans, 'g')} per 100 {panel['basis'].split(' ')[1]}"
        tiles.append({"id": "trans_fat", "kind": "nutrition", "tone": "worth", "title": "Trans fat",
                      "heading": "Worth a look: Trans fat", "amount": amount,
                      "where": f"{amount} on the nutrition table.",
                      "more": f"{amount} on the nutrition table. {NOTE_MORE}",
                      "body": list(tt["summary"]), "sources": _note_sources(tt),
                      "label_line": f"{trans['label']}: {trans['printed']}",
                      "source": {"kind": "nutrition", "ref": "trans_fat"}})
    partial = status == "partial"
    return {"title": NUTRITION_TITLE, "state": status, "basis": f"Per {panel['basis']}",
            "checked": NUTRITION_CHECKED, "rows": rows, "servings": servings,
            "also": (f"Also on the table, per {panel['basis']}: " + ", ".join(also) + ".") if also else None,
            "adults": NUTRITION_ADULTS if servings else None,
            "text": NUTRITION_PARTIAL if partial else None, "tiles": tiles, "sources": _nutrition_sources(),
            "ask_photo": False, "ask": None}


def _sugar_more(summary):
    """D-132 row 10: what ICMR-NIN and WHO say, added to the sugar answer. No new flag."""
    row = NOTES.get("sugar")
    sugar = next((r for r in summary if r["key"] == "sugar"), None)
    if sugar and sugar["source"]["ref"] and _note_shown(row):
        sugar["more"] = {"title": SUGAR_MORE_TITLE, "body": list(row["summary"]),
                         "sources": _note_sources(row)}


# D-127: "At a glance". Each list entry, as printed, gets one type, the most
# telling first. Counts, not weights: labels rarely print amounts, and the caption
# says so. The types' plain meanings are GLOSSARY below.
GLANCE_ORDER = ("worth", "sugar", "industrial", "additive", "other")
GLANCE_LABEL = {"worth": "Worth knowing", "sugar": "Sugar", "industrial": "Industrial",
                "additive": "Additive", "other": "Other"}
GLANCE_CAPTION = ("By number of ingredients, not weight: packs rarely print amounts. The strip is the "
                  "list in printed order, so what sits on the left there is most of.")
# D-134: the first screen has room for the first sentence; the strip's own ends say the second.
GLANCE_CAPTION_SHORT = "By number of ingredients, not weight: packs rarely print amounts."


def _glance(ingredients, sugar_found):
    if not ingredients:
        return None
    sugar_at = {p for p, _ in sugar_found}
    entries = []
    for n, text in enumerate(ingredients, start=1):
        flags = engine.analyze(text)["flags"]
        if any(f["type"] == "additive" and f["concern"] in ("moderate", "high") for f in flags):
            t = "worth"
        elif n in sugar_at:
            t = "sugar"
        elif any(f["type"] == "nova_marker" for f in flags):
            t = "industrial"
        elif any(f["type"] == "additive" for f in flags):
            t = "additive"
        else:
            t = "other"
        entries.append({"n": n, "text": text, "type": t})
    counts = {t: sum(e["type"] == t for e in entries) for t in GLANCE_ORDER}
    return {"total": len(entries), "counts": {t: c for t, c in counts.items() if c},
            "labels": GLANCE_LABEL, "entries": entries, "caption": GLANCE_CAPTION,
            "caption_short": GLANCE_CAPTION_SHORT}


# D-127: what the words on a result mean, for the ones this result used. Each links
# to its section of the "How we check" page (web/site/how.html).
GLOSSARY = {
    "sugar": ("Sugar", "Every added sugar on the list, under any of its names, such as liquid glucose "
              "or invert syrup. Ingredients are listed from most to least, so a sugar near the start "
              "is one of the main ingredients."),
    "industrial": ("Industrial ingredients", "Ingredients rarely used in home cooking, such as glucose "
                   "syrup, maltodextrin, emulsifiers or modified starch. Researchers use them to spot "
                   "\"ultra-processed\" food (NOVA group 4). It describes how a food is made."),
    "additive": ("Additive", "A substance added for a job, such as a colour, preservative or raising "
                 "agent, usually with an INS number. We check each one against FSSAI's list of "
                 "additives permitted in India."),
    "worth": ("Worth knowing", "An additive with research or a regulator's opinion a shopper may want to "
              "read. Tap its row to see what was found and where."),
    "permitted": ("Permitted in India", "FSSAI's additive rules allow it in food, either freely or up to "
                  "a limit for each kind of food."),
    "other": ("Other", "Everything else on the list, such as flour, oil, milk, salt or spices."),
    "allergen_line": ("Allergen line", "The line on the pack that starts with \"Contains\" or \"May "
                      "contain\". We read it together with the ingredients."),
}
HOW_URL = "/how"


def _glossary(summary, glance, adds, people):
    used = set()
    rows = {r["key"]: r for r in summary}
    if rows["sugar"]["source"]["ref"]:
        used.add("sugar")
    if rows["processing"]["chip"] == "Industrial":
        used.add("industrial")
    if adds:
        used.add("additive")
    if any((i["badge"] or {}).get("kind") == "worth_knowing" for i in adds):
        used.add("worth")
    if any((i["badge"] or {}).get("kind") == "permitted" for i in adds):
        used.add("permitted")
    if glance and glance["counts"].get("other"):
        used.add("other")
    if any(p["allergens"] for p in people):
        used.add("allergen_line")
    order = ("sugar", "industrial", "additive", "worth", "permitted", "other", "allergen_line")
    return [{"key": k, "term": GLOSSARY[k][0], "text": GLOSSARY[k][1], "url": f"{HOW_URL}#{k}"}
            for k in order if k in used]


def _alerts(adds):
    out = []
    for i in adds:
        if (i["badge"] or {}).get("kind") != "worth_knowing" or (i["badge"] or {}).get("note"):
            continue                         # not_permitted has its own alert; an unsure read, its note
        row = engine._ADDITIVE_BY_INS.get(i["ins"]) or {}
        klass = (row.get("class") or "additive").replace("_", " ")
        res = RESEARCH.get(i["ins"])
        out.append({
            "ins": i["ins"],
            "title": f"Worth a look: {i['name']} ({klass} {i['ins']})",
            "more": "Tap to see what research found" if res else "Tap to see why",
            "body": list(res["summary"]) if res else [i["why"]],
            "sources": [{"title": x["title"], "url": x["url"]} for x in res["sources"]] if res else [],
            "label_line": i.get("label_line") or i["label_text"],
            "checked": bool(res),
            "source": i["source"],
        })
    return out


# D-134: one screen. Every "Worth a look" row of the result, from wherever it came
# (an additive's badge, an ingredient note, the nutrition table), becomes one
# compact tile; tapping it opens its own page, built from `details[tile id]`. The
# tiles only regroup what the rows above already say: no new judgement, no new
# sentence about a pack (D-004, D-091). The older fields (additive_alert, alerts,
# ingredient_notes.tiles, nutrition.tiles) stay for app versions before web-27.
MORE_TITLE = "More about this pack"
TILE_KINDS = ("not_permitted", "additive", "ingredient", "nutrition")
CHECK_CHIP = "Check the number"


def _tile_id(kind, ref):
    """A tile id that sits in a URL (#/result/<id>/look/<tile id>) as it is."""
    return f"{kind}-" + "".join(ch for ch in str(ref).lower() if ch.isalnum() or ch == "_")


def _cites(sources):
    return [{"title": x["title"], "url": x["url"], "page": x.get("page") or None,
             "cite": x.get("cite") or x["title"] + (f", {x['page']}" if x.get("page") else "")} for x in sources]


def _misread(ins):
    return f"We read \"INS {ins}\" on the label. Check the pack: if we misread it, tap Report a mistake."


def _additive_tile(i):
    """An additive with a "Not permitted" or "Worth knowing" badge (D-111, D-125)."""
    row = engine._ADDITIVE_BY_INS.get(i["ins"]) or {}
    klass = (row.get("class") or "additive").replace("_", " ")
    badge = i["badge"]
    blocked = badge["kind"] == "not_permitted"
    res = RESEARCH.get(i["ins"])
    kind = "not_permitted" if blocked else "additive"
    tile = {"id": _tile_id("ins", i["ins"]), "kind": kind, "title": f"{i['name']} ({klass} {i['ins']})",
            "chip": CHECK_CHIP if badge.get("note") else badge["text"], "tone": "alert" if blocked else "worth",
            "source": i["source"]}
    detail = {"title": tile["title"], "chip": tile["chip"], "kind": kind,
              "what_it_is": f"{i['name']} is {_class_words(i['ins'])}, INS {i['ins']}.",
              "what_research_found": list(res["summary"]) if res else [i["why"]],
              "who_it_concerns": None,
              "on_the_label": i.get("label_line") or i["label_text"], "where": None,
              # The first thing on its page: FSSAI's list, or that the number itself may be a misread.
              "note": (f"{ADDITIVE_ALERT} {_misread(i['ins'])}" if blocked else badge.get("note")),
              "sources": _cites(res["sources"]) if res else []}
    return tile, detail


def _note_tile(n):
    """D-132: an ingredient note the review marked as a tile (palm oil, maida in the first 3...)."""
    row = NOTES[n["id"]]
    body = list(row["summary"])
    # `what_it_is` in the row: which of its reviewed sentences says what the ingredient
    # is (FSSAI's definition). The words are the reviewed ones; only the place changes.
    at = row.get("what_it_is")
    what = body.pop(at) if at is not None else None
    tile = {"id": _tile_id("note", n["id"]), "kind": "ingredient", "title": n["title"],
            "chip": n["where"][len("Listed "):].rstrip("."), "tone": "worth", "source": n["source"]}
    detail = {"title": n["title"], "chip": tile["chip"], "kind": "ingredient", "what_it_is": what,
              "what_research_found": body, "who_it_concerns": None, "on_the_label": n["label_line"],
              "where": n["where"], "note": None, "sources": n["sources"]}
    return tile, detail


def _nutrition_tile(t):
    """D-133: trans fat above zero on the nutrition table."""
    tile = {"id": _tile_id("nut", t["id"]), "kind": "nutrition", "title": t["title"],
            "chip": t["amount"], "tone": "worth", "source": t["source"]}
    detail = {"title": t["title"], "chip": t["amount"], "kind": "nutrition", "what_it_is": None,
              "what_research_found": list(t["body"]), "who_it_concerns": None, "on_the_label": t["label_line"],
              "where": t["where"], "note": None, "sources": t["sources"]}
    return tile, detail


def _tiles(adds, notes, nut):
    """
    D-134: (tiles, details). Order: an additive FSSAI doesn't permit, then the
    additives worth knowing (as their cards), then the ingredient notes (hydrogenated
    fat first, D-132), then the nutrition table.
    """
    made = [_additive_tile(i) for i in adds
            if (i["badge"] or {}).get("kind") in ("not_permitted", "worth_knowing")]
    made += [_note_tile(n) for n in (notes or {}).get("tiles") or []]
    made += [_nutrition_tile(t) for t in (nut or {}).get("tiles") or []]
    made.sort(key=lambda td: TILE_KINDS.index(td[0]["kind"]))
    return [t for t, _ in made], {t["id"]: d for t, d in made}


# D-123: what a result counts toward on "Your scans". The phone tallies these
# strings across its own history; the wording stays here, under the lint (D-091).
TALLY = {
    "sugar_early": "Sugar in the first 3 ingredients",
    "sugar_names": "Sugar under 2 or more names",
    "industrial": "Industrial ingredients",
    "additive": "An additive worth knowing",
}


def _tallies(summary):
    rows = {r["key"]: r for r in summary}
    out = []
    ref = rows["sugar"]["source"]["ref"]
    if ref and ref[0] <= 3:
        out.append(TALLY["sugar_early"])
    if rows["sugar"]["names"] > 1:
        out.append(TALLY["sugar_names"])
    if rows["processing"]["chip"] == "Industrial":
        out.append(TALLY["industrial"])
    if rows["additives"]["tone"] == "worth":
        out.append(TALLY["additive"])
    return out


# D-108: shown when a front photo was sent but couldn't be confirmed as this pack.
FRONT_NOT_USED = ("We couldn't confirm that the front and back photos are of the same pack, so the "
                  "front photo wasn't used. The result is from the back. If they are the same pack, "
                  "tick \"Both photos are of the same pack\" next time.")

# D-107: shown under a result for a pack without a barcode.
UNLISTED_NOTE = ("This pack has no barcode, so it isn't added to our catalogue. The result above "
                 "is from your photo, just for you.")
# D-167 (Sushil, 2026-10-07): a pack with a barcode and no checked (published) version yet,
# on its first scan and every scan before review. Review item 66: a tester asked why.
UNCHECKED_NOTE = ("We haven't checked this pack yet, so this result is read from your photo. Our team "
                  "checks it next, and then the next scan of this barcode is instant, for everyone.")


# D-130: a result read from a photo of a screen (a shop listing, a laptop).
# D-146: a code the scanner or a barcode photo read for a pack not in the catalogue is
# shown back, its first 3 and last 4 digits large, before the ingredients photo; a
# catalogue hit shows the product's name with a way back to the scanner. No typing (D-104).
BARCODE_CHECK_TITLE = "Check the barcode"
BARCODE_CHECK_TEXT = "Check these match the numbers under the barcode"
BARCODE_CHECK_YES = "Yes, they match"
BARCODE_CHECK_AGAIN = "Scan again"
RESCAN_TEXT = "Not this pack?"
RESCAN_BUTTON = "Scan again"

# D-175 (Sushil, 2026-10-08: "15 days will keep"): a published pack whose last check is
# older than this offers one optional photo of its ingredient list. The result comes first.
RECHECK_AFTER_DAYS = 15

# D-182: the pack picture, a reviewed photo of the pack's front shown when the shopper has no
# photo of their own (a barcode hit). It shows what the pack looks like; nothing is read from it.
PACK_PICTURE_ALT = "Photo of the front of the pack"
PACK_PICTURE_CAPTION = "Photo of the pack, checked by our team on {day}"


def pack_picture(picture, url_for):
    """{url, alt, caption} for a stored pack picture ({key, taken_on}), or None."""
    if not picture or not picture.get("key"):
        return None
    taken = str(picture.get("taken_on") or "")[:10]
    return {"url": url_for(picture["key"]), "alt": PACK_PICTURE_ALT,
            "caption": PACK_PICTURE_CAPTION.format(day=_day(taken)) if taken else None}
RECHECK_CARD = {"text": "Help keep this pack up to date: one photo of the ingredient list.",
                "button": "Photograph the ingredient list"}
RECHECKED = "Pack checked again on {day}."
# A photo match is a machine check, not our team's: the two dates stay apart (the advisor,
# Sushil agreeing, 2026-10-08, replacing D-175's rule 7).
TEAM_CHECKED = "Label last verified on {day}."
TEAM_AND_PHOTO = "Our team checked this label on {team}; a photo of the pack matched it on {photo}."


def checked_line(catalogue):
    """D-175: who checked the catalogue's label, and when; two dates when a photo matched it later."""
    team, photo = catalogue.get("team_verified"), catalogue.get("photo_matched")
    if team and photo and photo > team:
        return TEAM_AND_PHOTO.format(team=_day(team), photo=_day(photo))
    return TEAM_CHECKED.format(day=catalogue["last_verified"])


def checked_disclosure(team, photo=None):
    """The catalogue result's disclosure (D-024), with D-175's second date when a photo matched later."""
    first = (TEAM_AND_PHOTO.format(team=_day(team), photo=_day(photo)) if photo and photo > team
             else f"Our team last checked this label on {team}.")
    return first + " Packs change; if yours looks different, scan the back of the pack."


def barcode_check(code):
    """
    D-146: the digits to check against the pack, as printed under the bars: a UPC-A,
    kept here as 13 digits with a leading 0 (D-104), is printed as its 12.
    """
    shown = code[1:] if len(code) == 13 and code.startswith("0") else code
    return {"title": BARCODE_CHECK_TITLE, "text": BARCODE_CHECK_TEXT, "code": shown,
            "first": shown[:3], "middle": shown[3:-4], "last": shown[-4:],
            "yes": BARCODE_CHECK_YES, "again": BARCODE_CHECK_AGAIN}


# D-148: the daily photo-scan limit, shown in place of an error when an install
# has used its photo scans. The window is a rolling 24 hours (ratelimit.py), so the
# words give the time the next photo scan is free rather than "tomorrow". Barcode
# lookups have their own budget and still work. No upsell, and no result
# exists on this screen, so it carries no allergen line (D-060 needs a reading).
PHOTO_LIMIT_TITLE = "Photo scans used for now"
# D-184: no "during the beta" any more; the limit stays (cost control).
PHOTO_LIMIT_TEXT = "Each phone can photograph {limit} packs in any 24 hours."
PHOTO_LIMIT_BARCODE = "Scanning a barcode still works for packs we already know."
PHOTO_LIMIT_WHEN = "You can photograph another pack in about {n} {unit}."
PHOTO_LIMIT_SCAN = "Scan a barcode"


def photo_limit(seconds, limit):
    """D-148: the limit screen's words; `seconds` until the next photo scan is accepted."""
    minutes = max(1, -(-int(seconds) // 60))
    if minutes < 90:
        n, unit = minutes, "minute" if minutes == 1 else "minutes"
    else:
        n, unit = round(minutes / 60), "hours"
    return {"title": PHOTO_LIMIT_TITLE, "text": PHOTO_LIMIT_TEXT.format(limit=limit),
            "barcode": PHOTO_LIMIT_BARCODE, "when": PHOTO_LIMIT_WHEN.format(n=n, unit=unit),
            "scan": PHOTO_LIMIT_SCAN}


SCREEN_TITLE = "Read from a screen, not the pack."
SCREEN_TEXT = ("Listings can be out of date or show another size or flavour. "
               "Check the pack in the shop before you buy.")
SCREEN_PACK = "We also checked this pack in a shop on {day}; the allergen lines above include it."
SCREEN_NOTE = ("A screen isn't added to our catalogue: we only add packs read from the pack itself. "
               "Add it to your shop list and scan the pack when you're there.")
SCREEN_HEADLINE_UNREAD = "We couldn't read an ingredient list on this screen."
SCREEN_RETAKE = ("Take a screenshot that shows the whole ingredient list, zoomed in, "
                 "or photograph the pack in the shop.")


def _since_screen(profiles, screen_pack, ingredients, statement, confidence, reliable):
    """
    D-130: the pack in hand, scanned from the shop list, against the screenshot it
    was planned from. Allergens only, and only for avoid lists on this phone.
    """
    codes = list(dict.fromkeys(c for p in profiles for c in p["avoid"]))
    if not codes:
        return None
    then = allergen_checker.check(screen_pack["ingredients"], screen_pack["allergen_statement"], codes)
    now = allergen_checker.check(ingredients or [], statement, codes, confidence=confidence, reliable=reliable)
    if any(r.state == "cannot_confirm" for r in now.values()):
        return {"title": SINCE_TITLE, "lines": [SINCE_UNREAD], "differs": None}
    listed = ("contains", "may_contain")
    lines = []
    for c in codes:
        short = allergen_checker.ALLERGENS[c]["short"]
        a, b = then[c].state, now[c].state
        if b in listed and a not in listed:
            lines.append(f"{short[0].upper() + short[1:]} is listed on this pack. The screenshot didn't list it."
                         if b == "contains" else
                         f"This pack says it may contain {short}. The screenshot didn't.")
        elif a in listed and b not in listed:
            lines.append(f"{short[0].upper() + short[1:]} was on the screenshot. This pack doesn't list it.")
    return {"title": SINCE_TITLE, "lines": lines or [SINCE_SAME], "differs": bool(lines)}


SINCE_TITLE = "Compared with your screenshot"
SINCE_SAME = "The allergens on your avoid lists read the same on this pack as on the screenshot."
SINCE_UNREAD = "We couldn't read this pack clearly enough to compare it with the screenshot."


def build(**kw):
    """
    The `screen` block of a /scan response (_build() below), with D-188's split of the
    people: `people` holds the cards for the top of the result, a match or a line we can't
    confirm; `for_you` holds a child's age line; `for_you_note` the "may contain" reminder.
    """
    out = _build(**kw)
    cards, quiet, note = split_people(out["people"])
    for p in cards:
        if p["status"] in ("contains", "may_contain", "uncertain", "cannot_confirm"):
            # Share sends the lines without the nickname (D-074, D-177): "For your child: ...".
            whom = "you" if p["ref"] == "me" else NAME
            p["share"] = f"For {whom}, {p['line'][0].lower() + p['line'][1:]}"
    out["people"] = cards
    if quiet:
        out["for_you"] = quiet
    if note and out["state"] == "result":
        out["for_you_note"] = note
    return out


def _build(*, verdict, display, claim_check, extracted, reliability, profiles,
           allergen_confidence, allergen_reliable, catalogue=None, has_barcode=True,
           photos_sent=("back",), pack=None, screen_pack=None, nutrition=None, parts_sent=1, kind=None,
           nutra_input=None, barcode_answer=None, unchecked=False):
    """
    The `screen` block of a /scan response. verdict=None means the scan was refused.
    pack: for a result read from a screen (D-130), our catalogue's version of the
    same barcode ({ingredients, allergen_statement, verified_on}), or None.
    nutrition: the checked table from lenses/nutrition.check() (D-133), or None.
    parts_sent: how many back photos this scan joined (D-119), so the app knows
    whether one more photo, of the table, can still be added.
    kind: core/pack_kind.decide()'s answer (D-139, D-140), or None for ordinary food.
    barcode_answer: D-146's digit check answered in this scan ("confirmed", "rescanned"),
    so no second question is asked on its result.
    unchecked: D-167, the scan saved a version of a barcode that has no checked one yet.
    """
    ingredients = (extracted or {}).get("ingredients") or []
    statement = (extracted or {}).get("allergen_statement")
    from_screen = bool(reliability.get("from_screen"))
    baby = (baby_lines(kind["code"] if kind else "food", ingredients, allergen_reliable, nutrition)
            if verdict is not None else [])
    where = "pack" if (catalogue or {}).get("source") == "catalogue" else "photo"     # D-188
    people = [p for p in (_person(pr, ingredients, statement, allergen_confidence, allergen_reliable,
                                  screen=from_screen and verdict is not None, pack=pack, baby=baby,
                                  complete=reliability.get("ingredients_complete", True), where=where)
                          for pr in profiles) if p]

    if verdict is None and from_screen and reliability.get("error") not in ("product_mismatch", "not_a_food_pack"):
        # D-130: a screen we couldn't read. Nothing for a reviewer: there is no pack in it.
        return {
            "state": "retake",
            "people": people,
            "headline": {"text": SCREEN_HEADLINE_UNREAD,
                         "source": {"kind": "reliability", "ref": reliability.get("error")}},
            "retake": SCREEN_RETAKE,
            "problem": problem("screen_unread", SCREEN_RETAKE),
            "can_send": False,
        }

    if verdict is None:
        error = reliability.get("error")
        recipe = reliability.get("reason") == "recipe"
        blocked = error == "vision_blocked"                                       # D-172
        retake = ((RETAKE_RECIPE if recipe else None)
                  or (RETAKE_BLOCKED_NO_BARCODE if blocked and not has_barcode else None)
                  or (RETAKE_BACK.get(error) if "front" in photos_sent else None)
                  or RETAKE.get(error, RETAKE_DEFAULT))
        return {
            "state": "retake",
            "people": people,
            "headline": {"text": (HEADLINE_BACK.get(error) if "front" in photos_sent else None)
                                 or HEADLINE.get(error, "We couldn't read this label clearly."),
                         "source": {"kind": "reliability", "ref": error}},
            "retake": retake,
            "problem": problem("recipe" if recipe else error, retake),     # D-170
            # D-096/D-103: a pack we couldn't read can go to a reviewer; a photo
            # that isn't a pack can't, and neither can a pack without a barcode (D-107).
            "can_send": error not in NOT_A_PACK and error != "product_mismatch" and has_barcode,
            # D-172: a blocked read goes to a person after one scan, not D-070's two.
            "send_now": blocked and has_barcode,
        }

    if kind and kind["code"] != "food":
        out = _kind_screen(kind, people=people, ingredients=ingredients, reliability=reliability,
                           nutra_input=nutra_input, profiles=profiles)
        return _notes_for_every_result(out, catalogue=catalogue, profiles=profiles, screen_pack=screen_pack,
                                       ingredients=ingredients, statement=statement,
                                       allergen_confidence=allergen_confidence,
                                       allergen_reliable=allergen_reliable, from_screen=from_screen, pack=pack,
                                       has_barcode=has_barcode, reliability=reliability,
                                       parts=pack_kind.parts(kind["code"]), barcode_answer=barcode_answer)

    band = display["display_binary"]
    sure = (bool(allergen_reliable) and reliability.get("ingredients_complete", True)
            and (allergen_confidence or 0) >= allergen_checker.ALLERGEN_MIN_CONFIDENCE)
    worth, ordinary = _findings(verdict, sure)
    claims = _claim_rows(claim_check)
    complete = reliability.get("ingredients_complete", True)
    sugar_found = kids.sugar_positions(ingredients)
    # D-111: every count of ingredients on the screen is in one unit, and since D-173's
    # follow-up (Sushil, 2026-10-07: "yes") that unit is the list's printed entries, as the
    # pack shows them: 50 50 Maska Chaska prints 11, where the engine parses 20 parts
    # (palm, palmolein, 503, 341 ... each on its own). "Other" is the glance ring's own
    # count of entries nothing else on the screen names (sugar, industrial, additive).
    glance = _glance(ingredients, sugar_found)
    n_ord = ((glance or {}).get("counts") or {}).get("other", 0)
    n_list = len(ingredients)
    out = {
        "state": "result",
        "people": people,                                     # D-060: first
        "headline": _headline(band, worth, claims, reliability, sugar_found),
        # D-123: "No concerns found" never sits under a finding (Biscoff, 2026-09-27):
        # a clean band with anything worth knowing is shown as "a few things".
        "band": {"code": "mixed" if band == "clean" and worth else band,
                 "label": BAND_LABEL["mixed"] if band == "clean" and worth else BAND_LABEL.get(band, band),
                 "note": NOVA_NOTE if band == "ultra-processed" else None},
        # The scope line says what was checked; the claims (in shadow, D-051) join it.
        "checked": None,
        # D-173 wording follow-up (advisor, Sushil agreeing, 2026-10-08): a partly read list
        # says "we could read", never "on the list", which would claim the whole list.
        "scope": (f"We checked the {n_list} ingredient{'s' if n_list != 1 else ''} "
                  f"{'on the list' if complete else 'we could read'} against "
                  f"{len(engine._ADDITIVE_BY_INS)} additives and {len(engine.NOVA['markers'])} "
                  f"processing markers in our tables" + (", and the claims on the front." if claims else ".")),
        "claims": claims,
        "worth_knowing": worth,
        "ordinary": {"count": n_ord,
                     "text": (f"{n_ord} other ingredient{'s look' if n_ord != 1 else ' looks'} ordinary."
                              if n_ord else None),
                     "additives": ordinary},
        "ingredients": ingredients,
        "retake": None if reliability.get("ingredients_complete", True) else RETAKE_PARTIAL,
    }
    _partial_problem(out, reliability)
    # D-111: every additive as a card with its badge, most serious first. The same
    # items stay in worth_knowing / ordinary for older app versions.
    adds = sorted((i for i in worth + ordinary if i["source"]["kind"] == "additive"),
                  key=lambda i: _BADGE_ORDER.get((i["badge"] or {}).get("kind"), 3))
    for i in adds:
        # Quote the whole label line ("Raising agent (INS 503(ii))"), not the
        # engine's token ("ins 503(ii"), found with the one INS parser (D-099).
        i["label_line"] = next((line for line in ingredients if i["ins"] and i["ins"] in ins_numbers(line)),
                               i["label_text"])
    if adds:
        # Cards that need a look stay open; "Permitted" ones fold into one row, or
        # a label with twenty ordinary additives becomes a very long screen.
        folded = [i for i in adds if (i["badge"] or {}).get("kind") not in ("not_permitted", "worth_knowing")]
        n = len(folded)
        each = n and all((i["badge"] or {}).get("kind") == "permitted" for i in folded)
        out["additives"] = {
            "title": f"Additives on this pack ({len(adds)})",
            "items": adds,
            "open": len(adds) - n,
            "folded_text": (None if not n else
                            f"{n} {'more ' if n < len(adds) else ''}additive{'s' if n != 1 else ''}"
                            f"{', each permitted in India' if each and n > 1 else ', permitted in India' if each else ''}"),
        }
    # D-123: the three answers, right under the headline.
    summary = _summary(ingredients, sugar_found, worth, adds, complete)
    head = ("state", "people", "headline")
    out = {**{k: out[k] for k in head}, "summary": summary, **{k: v for k, v in out.items() if k not in head}}
    out["tallies"] = _tallies(summary)
    out["alerts"] = _alerts(adds)
    _sugar_more(summary)
    notes = _notes(ingredients, profiles, complete)
    if notes:
        out["ingredient_notes"] = notes
    nut = _nutrition(nutrition, parts_sent, catalogue)
    if nut:
        out["nutrition"] = nut
    # D-123 again: "No concerns found" never sits over a "Worth a look" row. The
    # words change; the engine's band and score don't (D-132, D-133: information only).
    tile = next(iter((notes or {}).get("tiles") or []), None) or next(iter((nut or {}).get("tiles") or []), None)
    if tile and out["headline"]["source"]["kind"] == "none":
        out["headline"] = {"text": BAND_LABEL["mixed"] + ".", "source": tile["source"]}
        out["band"] = {**out["band"], "code": "mixed", "label": BAND_LABEL["mixed"]}
    out["glance"] = glance
    out["glossary"] = _glossary(summary, out["glance"], adds, people)
    # D-134: the one-screen result. The allergen lines (people) stay first and apart.
    out["tiles"], out["details"] = _tiles(adds, notes, nut)
    out["more_title"] = MORE_TITLE
    alert = next((i for i in adds if (i["badge"] or {}).get("kind") == "not_permitted"), None)
    if alert:
        out["additive_alert"] = {
            "text": ADDITIVE_ALERT,
            "detail": _misread(alert["ins"]),
            "source": alert["source"],
        }
    # D-168: a catalogue pack with no nutrition table on file or on its way. Food only (the
    # other kinds return above), never from a screen (D-130); the app puts it last.
    if catalogue and catalogue.get("table_wanted") and has_barcode and not from_screen:
        out["table_offer"] = TABLE_OFFER
    return _notes_for_every_result(out, catalogue=catalogue, profiles=profiles, screen_pack=screen_pack,
                                   ingredients=ingredients, statement=statement,
                                   allergen_confidence=allergen_confidence, allergen_reliable=allergen_reliable,
                                   from_screen=from_screen, pack=pack, has_barcode=has_barcode,
                                   reliability=reliability, parts=pack_kind.PARTS["food"],
                                   barcode_answer=barcode_answer, unchecked=unchecked)


def _notes_for_every_result(out, *, catalogue, profiles, screen_pack, ingredients, statement,
                            allergen_confidence, allergen_reliable, from_screen, pack, has_barcode,
                            reliability, parts, barcode_answer=None, unchecked=False):
    """What any result says about where it came from, whatever the kind of pack."""
    # D-140: an infant or special medical result stays exactly as decided; the question waits.
    question = _band_question(profiles, barcode_answer)
    if question and (out.get("kind") or {}).get("code") not in ("infant", "special_medical"):
        out["band_question"] = question
    if catalogue and catalogue.get("source") == "catalogue":
        out["last_verified"] = checked_line(catalogue)
        # D-146: a catalogue hit shows the product's name; the app offers the way back to the scanner.
        out["rescan"] = {"text": RESCAN_TEXT, "button": RESCAN_BUTTON}
        # D-073: a barcode can outlive a recipe. Ask anyone with an avoid list for one back photo.
        if any(p["avoid"] for p in profiles):
            out["recheck"] = "Packs change. Photograph the back of your pack to re-check the avoid list."
        # D-175: last checked over RECHECK_AFTER_DAYS ago: one optional photo of the list. One
        # ask per scan: D-073's, when it shows, does the same job, so this one waits.
        elif catalogue.get("recheck_due"):
            out["recheck_card"] = dict(RECHECK_CARD)
        if catalogue.get("rechecked_on"):
            out["rechecked"] = RECHECKED.format(day=_day(catalogue["rechecked_on"]))
    if screen_pack:
        since = _since_screen(profiles, screen_pack, ingredients, statement, allergen_confidence,
                              allergen_reliable)
        if since:
            out["since_screen"] = since
    if from_screen:
        # D-130: say where the result came from, first thing under the people lines.
        out["from_screen"] = {"title": SCREEN_TITLE, "text": SCREEN_TEXT,
                              "pack": (SCREEN_PACK.format(day=_day(pack["verified_on"])) if pack else None)}
        out["catalogue_note"] = SCREEN_NOTE
        if "shop_list" in parts:
            out["shop_list"] = True           # the app offers "Add to my shop list"
    elif not has_barcode:
        out["catalogue_note"] = UNLISTED_NOTE
    elif unchecked:
        out["catalogue_note"] = UNCHECKED_NOTE
    # D-108: a front that couldn't be tied to this back is not used; say so.
    if any(c.get("code") == "product_pairing_unverified" for c in reliability.get("caveats", [])):
        out["front_note"] = FRONT_NOT_USED
    return out


# D-139, D-140: a pack that isn't ordinary food gets a short result. Its words are
# here, under the wording lint (D-091); which parts show is data/pack_kinds.json.
# Allergen lines stay first for every kind (D-060).
KIND_TEXT = {
    # D-139 phase 2: a supplement is checked against FSSAI's rules for supplements, not the food checks.
    "supplement": ("We check a supplement against FSSAI's rules for supplements, as operationalised by FSSAI's "
                   "direction of 18 October 2022, and ICMR-NIN's nutrient requirements, not against our checks "
                   "for foods."),
    "special_medical": ("We show the allergens on the list and nothing else for a food for special dietary "
                        "or medical use."),
    # D-140 (Sushil, 2026-09-30): until the lawyer answers, one sentence and nothing else about the food.
    "infant": "Results for infant foods aren't shown yet. We show the allergens on the list and the ingredient list.",
    "not_food": ("Our checks follow FSSAI's food rules, and the Food Safety and Standards Act, 2006 leaves "
                 "\"drugs and medicinal products\" out of \"food\" (section 3(1)(j)). We show the allergens "
                 "on the list and nothing else."),
}
NOT_FOOD_HEADLINE = "We didn't find an FSSAI licence number on the photos."
# A kind known only from our catalogue's category, with no words printed to quote.
CATEGORY_HEADLINE = {
    "supplement": "Filed in our catalogue as a food supplement.",
    "infant": "Filed in our catalogue as a food for infants.",
    "special_medical": "Filed in our catalogue as a food for special dietary or medical use.",
}
# The printed words the headline quotes first: the product's own kind name before a notice.
_HEADLINE_RULES = ("infant_names", "traditional", "supplement_words", "fsmp", "fsdu", "preterm",
                   "hypoallergenic", "mono_grain", "medical_advice", "dietary_management", "six_months",
                   "mothers_milk")
FSS_ACT_SOURCE = {"title": "Food Safety and Standards Act, 2006, section 3(1)(j)",
                  "url": "https://fssai.gov.in/upload/uploadfiles/files/FOOD-ACT.pdf", "page": "PDF p. 2",
                  "cite": "Food Safety and Standards Act, 2006, section 3(1)(j)"}


# D-139 phase 2: a supplement's own checks (lenses/nutra.py); every sentence here.
UNIT_TEXT = {"mg": "mg", "ug": "\u00b5g", "g": "g", "IU": "IU"}
NUTRA_SOURCE = nutra.RULES["_meta"]["sources"]["nutra"]
ICMR_SOURCE = nutra.RULES["_meta"]["sources"]["icmr_rda"]
TUL_DEFINITION = ("ICMR-NIN: \"The TUL is the maximum level of habitual intake from all sources of a nutrient or "
                  "related substance judged to be unlikely to lead to adverse health effects in humans.\"")
SUPPLEMENT_TITLES = {"children": "For children", "amounts": "Amounts beside ICMR-NIN's RDA",
                     "statements": "What FSSAI's rules ask the label to say", "additives": "Additives",
                     "protein": "Protein powder"}
_FORMAT_WORDS = {"tablet_capsule_syrup": "tablets, capsules and syrups", "supplements_13_6": "supplements"}


def _cite(src, page=None):
    return {"title": src["title"], "url": src["url"], "page": page,
            "cite": src["title"] + (f", {page}" if page else "")}


def _n(x):
    return _fmt(x, 2)


def _rda_words(r):
    u = UNIT_TEXT[r["unit"]]
    rda = (f"ICMR-NIN's RDA for adults is {_n(r['rda_men'])} {u} a day" if r["rda_men"] == r["rda_women"] else
           f"ICMR-NIN's RDA is {_n(r['rda_men'])} {u} a day for adult men and {_n(r['rda_women'])} {u} for adult women")
    tul = f", and its upper limit for adults is {_n(r['tul'])} {u} a day" if r["tul"] is not None else ""
    return rda + tul + "."


def _supplement_parts(kind, *, ingredients, vision, ocr_text, profiles, product=None):
    """(tiles, details, sections, summary) for a supplement (D-139). vision None: a catalogue
    result, with its published name (`product`) and list but no photos to read."""
    vision = vision or {}
    tiles, details, sections = [], {}, []
    fmt = nutra.format_of(vision or {"product": product or {}})
    child = any(p["age"] in kids.AGE_BANDS and p["age"] != "young" for p in profiles)

    if child:
        sections.append({"id": "children", "title": SUPPLEMENT_TITLES["children"],
                         "lines": ["FSSAI's rules for supplements say products for children of 2 to 5 years \"shall only "
                                   "be given under medical advice by a recognized medical doctor or dietician or "
                                   "nutritionist\"."],
                         "sources": [_cite(NUTRA_SOURCE, "5(10), Annexure 1 p. 5")]})

    # Plants with a note in Schedule II: a tile each, the note quoted as printed.
    hits = nutra.plants(ingredients, vision)
    hits.sort(key=lambda h: not (child and set(h["row"]["who"]) & {"under_5", "under_16", "children"}))
    for h in hits:
        row = h["row"]
        tid = _tile_id("plant", row["id"])
        title = f"{row['botanical'][0]}, {row['part'].lower()}"
        found = [f"FSSAI's schedule of plants for supplements says, for this part: \"{row['note']}\"."]
        if row.get("placement"):
            found.append(f"The schedule's layout: {row['placement']}")
        if child:
            found.append("The schedule gives children 5 to 16 years half the adult range and children 2 to 5 years "
                         "a quarter of it.")
        tiles.append({"id": tid, "kind": "supplement", "title": title, "chip": row["note"], "tone": "worth",
                      "source": {"kind": "plant", "ref": row["id"]}})
        details[tid] = {"title": title, "chip": row["note"], "kind": "supplement",
                        "what_it_is": (f"FSSAI's schedule lists {row['botanical'][0]} ({row['part'].lower()}) at "
                                       f"{row['usage_adult_per_day']} a day for adults."),
                        "what_research_found": found, "who_it_concerns": None, "on_the_label": h["entry"],
                        "where": None, "note": None,
                        "sources": [_cite(NUTRA_SOURCE, row["fssai_basis"].split(", read")[0])]}

    # Amounts in a day's usage beside ICMR-NIN's RDA (never called a limit) and upper limit.
    if vision.get("composition") is not None or vision.get("pack_statements") is not None:
        a = nutra.amounts(vision, ocr_text)
        lines = []
        if a["state"] == "not_read":
            lines.append("We didn't find a table of amounts per tablet, capsule or serving in the photos.")
        elif a["state"] == "unverified":
            lines.append("We couldn't check the amounts against a second reading of the photo, so they aren't shown.")
        elif a["rows"]:
            if a["daily"]:
                lines.append(f"A day's usage, as the pack says: \"{a['daily']['text']}\".")
            elif a.get("per"):
                lines.append(f"Amounts in one {a['per']['unit']}, as printed. We couldn't read how many a day the "
                             "pack says to take, so a day's amounts aren't worked out.")
            for r in a["rows"]:
                u = UNIT_TEXT[r["unit"]]
                amount = (f"{_n(r['value'])} {u} a day" if a["daily"] else
                          f"{_n(r['value'])} {u} in one {a['per']['unit']}" if a.get("per") else r["printed"])
                lines.append(f"{r['label'][0].upper() + r['label'][1:]}: {amount}. {_rda_words(r)}")
                if r["note"] and r["nutrient"] == "magnesium":
                    lines.append(f"ICMR-NIN's note: \"{r['note']}\"")
                if r["over_tul"]:
                    tid = _tile_id("tul", r["nutrient"])
                    title = f"{r['label'][0].upper() + r['label'][1:]}: {_n(r['value'])} {u} a day"
                    chip = "Above ICMR-NIN's upper limit for adults"
                    tiles.append({"id": tid, "kind": "supplement", "title": title, "chip": chip, "tone": "worth",
                                  "source": {"kind": "tul", "ref": r["nutrient"]}})
                    details[tid] = {"title": title, "chip": chip, "kind": "supplement", "what_it_is": None,
                                    "what_research_found": [f"ICMR-NIN's upper limit for adults is {_n(r['tul'])} {u} "
                                                            f"a day.", TUL_DEFINITION]
                                    + ([f"ICMR-NIN's note: \"{r['note']}\""] if r["note"] else []),
                                    "who_it_concerns": None, "on_the_label": f"{r['line']}: {r['printed']}",
                                    "where": f"A day's usage, as the pack says: \"{a['daily']['text']}\".",
                                    "note": None, "sources": [_cite(ICMR_SOURCE, "pp. 30 to 32")]}
        if lines:
            sections.append({"id": "amounts", "title": SUPPLEMENT_TITLES["amounts"], "lines": lines,
                             "sources": [_cite(ICMR_SOURCE, "pp. 30 to 32")]})

    # The statements 5(12) asks for, found or not found, only on a complete read of both faces.
    if vision:
        checked = nutra.statements(vision, ocr_text)
        if checked is None:
            lines = ["We need clear photos of the whole front and back to check the statements FSSAI's rules ask "
                     "for."]
        else:
            ask = {r["id"]: r["ask"] for r in nutra.RULES["statements"]}
            found = [c for c in checked if c["found"]]
            lines = [f"FSSAI's rules for health supplements ask the label for {ask[c['id']]}. We didn't find it on "
                     f"the photos of this pack." for c in checked if not c["found"]]
            if found:
                lines.append("Found on the pack, as the rules ask: " +
                             ", ".join(f"\"{c['printed']}\"" for c in found) + ".")
        sections.append({"id": "statements", "title": SUPPLEMENT_TITLES["statements"], "lines": lines,
                         "sources": [_cite(NUTRA_SOURCE, "5(12), Annexure 1 pp. 5 to 6")]})

    # Additives against the list for this format; "not found" is never "not permitted".
    adds = nutra.additives(ingredients, fmt)
    if adds:
        lines = []
        listed = [x for x in adds if x["listed"]]
        if listed:
            where = _FORMAT_WORDS[listed[0]["where"]]
            lines.append(f"In the additive lists FSSAI's supplement rules point to for {where}: "
                         + ", ".join(dict.fromkeys(x["entry"] for x in listed)) + ".")
        for x in adds:
            if x["listed"] is None:
                lines.append(f"\"{x['entry']}\": FSSAI's list for tablets and capsules allows \"Colors permitted "
                             "under Rule 127 of Drugs & Cosmetics Rules including lake colours\", a list we haven't "
                             "read, so this colour isn't checked.")
            elif x["listed"] is False:
                where = _FORMAT_WORDS[x["where"]]
                tid = _tile_id("add", x["ins"] or x["entry"])[:48]
                title, chip = x["name"] or x["entry"], "Not found in FSSAI's supplement lists"
                text = (f"We didn't find it in the additive lists FSSAI's supplement rules point to for {where} "
                        "(Annexure 3 and Appendix A's GMP table).")
                lines.append(f"\"{x['entry']}\": {text}")
                if tid not in details:
                    tiles.append({"id": tid, "kind": "additive", "title": title, "chip": chip, "tone": "worth",
                                  "source": {"kind": "nutra_additive", "ref": x["ins"] or x["entry"]}})
                    details[tid] = {"title": title, "chip": chip, "kind": "additive", "what_it_is": None,
                                    "what_research_found": [text, "Names on packs vary, so a person checks it too."],
                                    "who_it_concerns": None, "on_the_label": x["entry"], "where": None, "note": None,
                                    "sources": [_cite(NUTRA_SOURCE, "5(4)(a), p. 4; 6(1)(e), p. 8; Annexure 3, pp. 68 to 75")]}
        sections.append({"id": "additives", "title": SUPPLEMENT_TITLES["additives"], "lines": lines,
                         "sources": [_cite(NUTRA_SOURCE, "5(4)(a), p. 4; 6(1)(e), p. 8; Annexure 3, pp. 68 to 75")]})

    # A protein powder: ICMR-NIN's own sentences, with the page (Sushil, D-139 choice 5).
    if nutra.protein_powder(vision, fmt):
        pp = nutra.RULES["protein_powder"]
        sections.append({"id": "protein", "title": SUPPLEMENT_TITLES["protein"],
                         "lines": ["ICMR-NIN's dietary guidelines say: \"" + pp["quotes"][0] + "\" and \""
                                   + pp["quotes"][1] + "\""],
                         "sources": [_cite(pp["source"], pp["source"]["page"])]})

    # The sugar answer only for a supplement in a food format (gummies, powders, bars).
    summary = None
    if fmt == "food" and ingredients:
        summary = [_summary(ingredients, kids.sugar_positions(ingredients), [], [], True)[0]]
    return tiles, details, sections, summary


def _kind_screen(kind, *, people, ingredients, reliability, nutra_input=None, profiles=()):
    """The result for a supplement, an infant food, a special medical food or a pack that isn't food."""
    code, parts = kind["code"], pack_kind.parts(kind["code"])
    printed = [e for e in kind["evidence"] if not e.get("supporting") and e.get("rule") != "catalogue_category"]
    shown = min(printed, key=lambda e: (_HEADLINE_RULES.index(e["rule"]) if e.get("rule") in _HEADLINE_RULES
                                        else len(_HEADLINE_RULES)), default=None)
    if code == "not_food":
        headline = NOT_FOOD_HEADLINE
    elif shown:
        headline = f"This pack says \"{shown['text']}\"."        # the kind in the pack's own words
    else:
        headline = CATEGORY_HEADLINE[code]
    lines = [KIND_TEXT[code]]
    if code == "not_food":
        lines.insert(0, f"The pack prints \"{shown['text']}\".")
    out = {
        "state": "result",
        "people": people,                                     # D-060: first, for every kind
        "headline": {"text": headline, "source": {"kind": "pack_kind", "ref": code}},
        "kind": {"code": code, "lines": lines,
                 "evidence": [{"text": e["text"], "face": e.get("face")} for e in kind["evidence"]],
                 "sources": [FSS_ACT_SOURCE] if code == "not_food" else []},
        "parts": list(parts),
        "ingredients": ingredients,
        "retake": None if reliability.get("ingredients_complete", True) else RETAKE_PARTIAL,
        "more_title": MORE_TITLE,
        "checked": "We checked the ingredients against your avoid lists.",
    }
    _partial_problem(out, reliability)
    if code == "supplement":
        tiles, details, sections, summary = _supplement_parts(
            kind, ingredients=ingredients, vision=(nutra_input or {}).get("vision"),
            ocr_text=(nutra_input or {}).get("ocr_text"), profiles=profiles,
            product=(nutra_input or {}).get("product"))
        out["tiles"], out["details"], out["sections"] = tiles, details, sections
        if summary:
            out["summary"] = summary
    return out

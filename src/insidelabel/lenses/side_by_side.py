"""
side_by_side.py - Compare for supplements and infant foods: facts side by side, no pick (D-200).

Food's Compare names "the better pick of these for a child" by D-057's concern tiers.
Those tiers are for food over 2 years, and no source we read ranks one supplement above
another, or one infant food above another. So for these two kinds /compare sets each pack's
facts beside the others' and names no winner: no "better pick", no tie, no order but the
order the packs were added, no count of findings (a count would be a score, D-004).
D-201 (Sushil, 2026-10-13) adds, for infant foods, one pack's own facts as numbers: how many
of the nutrients we compared sit outside FSSAI's range ("1 of 27: Protein ...") and how many
of regulation 4's notices were seen. Each is that pack's fact against FSSAI's table, never a
total across rows, a tally across packs or an order.

- A pack compares only with packs of its own kind (api/main.py refuses a mixed request).
- Allergens come first for each pack (D-060), shown only on a match or a line we can't
  confirm (D-188).
- Supplements: amounts per day beside ICMR-NIN's RDA for men and women ("RDA" is never
  called a limit, D-139), the upper-limit lines, the plant notes and the additives against
  the list for the format. No child line: FSSAI's 5(10) says supplements for children of
  2 to 5 "shall only be given under medical advice".
- Infant foods: D-140's checks (lenses/infant.py) in lenses/screen.py's own sentences;
  D-201: the age or stage printed, the added sugar, protein beside FSSAI's range (with the
  range bar's numbers), the nutrients outside FSSAI's range and the notices seen.
  Never mother's milk as a column or a reference (IMS Act 3(b)); no feeding advice (7(1)).

The phone sends back what /scan read from the photos (`facts`, see screen.compare_input);
everything worked out from the ingredient list, and every word, is done here again.
"""

import re

from insidelabel.lenses import allergens as allergen_check
from insidelabel.lenses import diet as diet_check
from insidelabel.lenses import infant as infant_lens
from insidelabel.lenses import nutra, nutrition
from insidelabel.lenses.compare import sugar_positions
from insidelabel.lenses import screen

HEADING = {
    "supplement": "These supplements, side by side",
    "infant": "These infant foods, side by side",
}
NOTE = {
    "supplement": ("Each label's facts beside FSSAI's rules for supplements and ICMR-NIN's RDA. We don't name a "
                   "pick between supplements."),
    "infant": ("Each label's facts beside FSSAI's rules for foods for infant nutrition. We don't name a pick between "
               "infant foods: no source we read ranks one above another."),
}
TITLES = {
    "usage": "A day's usage, as printed", "amounts": "A day's amounts beside ICMR-NIN's RDA",
    "upper": "Above ICMR-NIN's upper limit for adults",
    "plants": "Plant notes", "additives": "Additives", "type": "Kind of infant food (sets the checks)",
    "words": "Words the rules say not to use",
    "free_from": "Preservatives, colours and flavours (5(1) leaves them out)",
    "hydrogenated": "Hydrogenated fat",
    # D-201
    "age": "Age or stage, as printed", "sugar": "Added sugar",
    "protein": "Protein per 100 g, beside FSSAI's range", "outside": "Nutrients outside FSSAI's range",
    "notices": "Notices FSSAI's rules ask for",
}
NOT_READ = "Not read from the photos of this pack."
NOTHING = "Nothing found."
NO_TYPE = "Off: the pack's name doesn't say which kind of infant food it is."
NO_NUMBERS = "No number from the pack's table per 100 g to set beside it."
NO_AGE = "Not seen on the photos."
NO_SUGAR = "Nothing found on the list."
NO_ADDED = "Added sugars: not printed."
# Every pack gets every row, in this order, so the app lines them up across the packs.
KEYS = {"supplement": ("usage", "amounts", "upper", "plants", "additives"),
        "infant": ("type", "age", "sugar", "protein", "outside", "notices", "words", "free_from", "hydrogenated",
                   "additives")}
_RDA = {r["nutrient"]: r for r in nutra.RULES["rda"]}
SOURCES = {
    "supplement": [screen._cite(screen.NUTRA_SOURCE), screen._cite(screen.ICMR_SOURCE, "pp. 30 to 32")],
    "infant": [screen._cite(screen.INFANT_SOURCE)],
}


def _row(key, lines, bar=None):
    out = {"key": key, "title": TITLES[key], "lines": lines or [NOTHING]}
    if bar:
        out["bar"] = bar                            # D-201: the range bar's numbers (the app draws them)
    return out


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


# ---------------------------------------------------------------- supplements

def supplement_rows(ingredients, facts):
    facts = facts or {}
    rows = []
    a = facts.get("amounts") or {}
    usable = [r for r in a.get("rows") or [] if r.get("nutrient") in _RDA and _number(r.get("value"))]
    daily = a.get("daily") if isinstance(a.get("daily"), dict) else None
    per = a.get("per") if isinstance(a.get("per"), dict) else None
    if a.get("state") != "shown":
        rows += [_row("usage", [NOT_READ]), _row("amounts", [NOT_READ]), _row("upper", [NOT_READ])]
    else:
        rows.append(_row("usage", [f"\"{daily['text']}\"" if daily else
                                   "We couldn't read how many a day the pack says to take."]))
        lines, upper = [], []
        for r in usable:
            rda = _RDA[r["nutrient"]]
            u = screen.UNIT_TEXT[rda["unit"]]
            label = rda["label"][0].upper() + rda["label"][1:]
            amount = (f"{screen._n(r['value'])} {u} a day" if daily else
                      f"{screen._n(r['value'])} {u} in one {per['unit']}" if per else f"{screen._n(r['value'])} {u}")
            rda_words = (f"RDA {screen._n(rda['rda_men'])} {u}" if rda["rda_men"] == rda["rda_women"] else
                         f"RDA men {screen._n(rda['rda_men'])} {u}, women {screen._n(rda['rda_women'])} {u}")
            lines.append(f"{label}: {amount} ({rda_words}).")
            if daily and rda["tul_adult"] is not None and r["value"] > rda["tul_adult"]:
                upper.append(f"{label}: {screen._n(r['value'])} {u} a day; the upper limit for adults is "
                             f"{screen._n(rda['tul_adult'])} {u}.")
        rows.append(_row("amounts", lines))
        rows.append(_row("upper", upper))
    entries = list(ingredients or []) + [x for x in facts.get("composition_names") or [] if isinstance(x, str)]
    rows.append(_row("plants", [f"{h['row']['botanical'][0]}, {h['row']['part'].lower()}: \"{h['row']['note']}\""
                                for h in nutra.plants(entries)]))
    fmt = facts.get("format") if facts.get("format") in ("tablet_capsule_syrup", "supplements_13_6", "food") else None
    adds = nutra.additives(ingredients, fmt) if fmt else []
    lines = []
    for x in adds:
        if x["listed"] is False:
            lines.append(f"\"{x['entry']}\": not found in the lists for {screen._FORMAT_WORDS[x['where']]}.")
        elif x["listed"] is None:
            lines.append(f"\"{x['entry']}\": a colour in a tablet, not checked.")
    if adds and not lines:
        lines.append("All in the lists for this format.")
    rows.append(_row("additives", lines))
    return rows


# ---------------------------------------------------------------- infant foods

def _type_of(facts):
    t = (facts or {}).get("type")
    if isinstance(t, dict) and t.get("id") in screen.INFANT_TYPE_WORDS and isinstance(t.get("printed"), str):
        row = next(r for r in infant_lens.RULES["types"] if r["id"] == t["id"])
        return {"id": row["id"], "chapter": row["chapter"], "printed": t["printed"], "basis": row["basis"]}
    return None


def _statements(facts):
    texts = {r["id"]: r for r in infant_lens.RULES["statements"]}
    got = (facts or {}).get("statements")
    if not isinstance(got, list):
        return None
    out = []
    for r in got:
        if isinstance(r, dict) and r.get("id") in texts:
            printed = r.get("printed") if isinstance(r.get("printed"), str) else None
            out.append({"id": r["id"], "text": texts[r["id"]]["text"], "found": bool(r.get("found") and printed),
                        "printed": printed})
    return out


def _composition(facts, ptype):
    """The nutrients the phone read, beside the type's table: [{nutrient, label, value, unit, range}]."""
    if ptype is None or ptype["id"] not in infant_lens.COMPOSITION["types"]:
        return []
    table = {r["nutrient"]: r for r in infant_lens.COMPOSITION["types"][ptype["id"]]["rows"]}
    out = []
    for r in (facts or {}).get("composition") or []:
        if not isinstance(r, dict) or r.get("nutrient") not in table or not _number(r.get("value")):
            continue
        row = table[r["nutrient"]]
        # D-200 (advisor): the number and the table's range only; no below/above/within field,
        # so those words can't reach a screen later. D-201's "outside" is worked out here.
        out.append({"nutrient": r["nutrient"], "label": str(r.get("label") or r["nutrient"]),
                    "value": float(r["value"]), "unit": row["unit"], "range": row["per_100_g"]})
    return out


def _outside(r):
    lo, hi = r["range"]
    return (lo is not None and r["value"] < lo) or (hi is not None and r["value"] > hi)


INFANT_TYPE = {k: v[0].upper() + v[1:] for k, v in screen.INFANT_TYPE_WORDS.items()}
TYPE_SHORT = "{}, from the pack's name."
NO_TYPE_SHORT = "Not known from the pack's name."
FREE_FROM_WORD = {"preservative": "a preservative", "colour": "a colour", "flavour": "a flavour"}


def _printed_number(x):
    """A printed number the phone sent back ("18", "0.5"), or None."""
    return x if isinstance(x, str) and re.fullmatch(nutrition._NUM, x.strip()) else None


def _sugar_lines(ingredients, facts):
    pos = sugar_positions(ingredients or [])
    n = len(ingredients or [])
    if pos:
        at, first = pos[0]
        lead = (f"Sugar is the {screen._ordinal(at)} of {n} ingredients." if first == "sugar" else
                f"Added sugar comes {screen._ordinal(at)} of {n} ingredients, as {first}.")
    else:
        lead = NO_SUGAR
    sugars = facts.get("sugars") if isinstance(facts.get("sugars"), dict) else None
    if sugars is None:
        return [lead]
    added = _printed_number(sugars.get("added"))
    return [lead, f"Added sugars: {added} g per 100 g, as printed." if added else NO_ADDED]


def _span(r):
    lo, hi = r["range"]
    u = screen._UNIT.get(r["unit"], r["unit"])
    return screen._span(lo, hi, u)


def infant_rows(ingredients, facts):
    facts = facts or {}
    ptype = _type_of(facts)
    rows = [_row("type", [TYPE_SHORT.format(INFANT_TYPE[ptype["id"]]) if ptype else NO_TYPE_SHORT])]
    age = facts.get("age") if isinstance(facts.get("age"), str) and facts.get("age").strip() else None
    rows.append(_row("age", [f"\"{age.strip()[:40]}\"" if age else NO_AGE]))
    rows.append(_row("sugar", _sugar_lines(ingredients, facts)))
    comp = _composition(facts, ptype)
    if ptype is None:
        rows += [_row("protein", [NO_TYPE]), _row("outside", [NO_TYPE])]
    else:
        protein = next((r for r in comp if r["nutrient"] == "protein"), None)
        if protein:
            u = screen._UNIT.get(protein["unit"], protein["unit"])
            lo, hi = protein["range"]
            rows.append(_row("protein", [f"{screen._fmt(protein['value'])} {u}. FSSAI's range: {_span(protein)}."],
                             bar=screen.infant_bar(protein["value"], lo, hi, u)))
        else:
            rows.append(_row("protein", [NO_NUMBERS if ptype["id"] != "traditional" else
                                         "FSSAI's rules for this kind have no composition table."]))
        out = [r for r in comp if _outside(r)]
        if not comp:
            rows.append(_row("outside", [NO_NUMBERS if ptype["id"] != "traditional" else
                                         "FSSAI's rules for this kind have no composition table."]))
        elif out:
            rows.append(_row("outside", [f"{len(out)} of {len(comp)}: " + "; ".join(
                f"{r['label'][0].upper() + r['label'][1:]} {screen._fmt(r['value'])} "
                f"{screen._UNIT.get(r['unit'], r['unit'])} (range {_span(r)})" for r in out) + "."]))
        else:
            rows.append(_row("outside", [f"None of {len(comp)}."]))
    statements = _statements(facts)
    no_milk = facts.get("no_milk") if isinstance(facts.get("no_milk"), dict) else None
    if no_milk is not None:
        no_milk = {"text": infant_lens.RULES["no_milk"]["text"], "found": bool(no_milk.get("found")),
                   "printed": no_milk.get("printed") if isinstance(no_milk.get("printed"), str) else None}
        no_milk["found"] = no_milk["found"] and bool(no_milk["printed"])
    if statements is None:
        rows.append(_row("notices", [NOT_READ]))
    else:
        every = statements + ([no_milk] if no_milk else [])
        seen = sum(1 for r in every if r["found"])
        photos = facts.get("photos") if isinstance(facts.get("photos"), int) and 0 < facts["photos"] <= 9 else None
        rows.append(_row("notices", [f"Seen: {seen} of {len(every)}" +
                                     (f", on {photos} photo{'s' if photos > 1 else ''}." if photos else ".")]))
    words = [w for w in facts.get("words") or [] if isinstance(w, dict)
             and w.get("word") in infant_lens.RULES["words_not_to_use"]["words"]]
    rows.append(_row("words", [f"\"{w['word'].title()}\"" for w in words]))
    rows.append(_row("free_from", [f"\"{x['entry']}\" ({FREE_FROM_WORD[x['why'][0]]})"
                                   for x in infant_lens.free_from(ingredients)]))
    if ptype is None:
        return rows + [_row(k, [NO_TYPE]) for k in ("hydrogenated", "additives")]
    rows.append(_row("hydrogenated", [f"\"{x['entry']}\"" for x in infant_lens.hydrogenated(ingredients, ptype)]
                     or ([NOTHING] if ptype["id"] != "traditional" else
                         ["FSSAI's rules for this kind say nothing about it."])))
    adds = infant_lens.additives(ingredients, ptype)
    rows.append(_row("additives", [f"\"{x['entry']}\": INS {x['ins']} not found in this kind's list."
                                   for x in adds["not_found"]] or ["All in this kind's list."]))
    return rows


# ---------------------------------------------------------------- the comparison

def compare(kind, packs, avoid=(), who=None):
    """
    packs: [{id, name, ingredients, allergen_statement, confidence, reliable, veg_mark, facts}].
    The answer has no best, tie or ranking field at all: only each pack's facts, in the order sent.
    """
    who = who or "you"
    codes = [c for c in avoid if c in allergen_check.ALLERGENS]
    diet_codes = [c for c in avoid if c in diet_check.DIETS]
    out = []
    for p in packs:
        found = allergen_check.check(p["ingredients"], p.get("allergen_statement"), codes,
                                     confidence=p.get("confidence", 1.0), reliable=p.get("reliable", True))
        diet = diet_check.check(p["ingredients"], diet_codes, veg_mark=p.get("veg_mark"),
                                confidence=p.get("confidence", 1.0), reliable=p.get("reliable", True),
                                product_name=p["name"])
        rows = (supplement_rows if kind == "supplement" else infant_rows)(p["ingredients"], p.get("facts"))
        out.append({
            "id": p["id"], "name": p["name"],
            # D-188: only a match or a line we can't confirm; "not listed" stays out.
            "allergens": [{"code": r.code, "state": r.state, "text": r.parent_text(who)}
                          for r in found.values() if r.state != "not_listed"],
            "diet": [{"code": r.code, "state": r.state, "text": diet_check.text(r)}
                     for r in diet.values() if r.state != "not_listed" and not diet_check.green_quiet(r)],
            "rows": rows,                          # KEYS[kind], in that order, for every pack
            "fully_read": bool(p.get("reliable", True)),
        })
    return {"outcome": "side_by_side", "kind": kind, "heading": HEADING[kind], "note": NOTE[kind],
            "who": who, "avoid": list(avoid), "packs": out, "sources": SOURCES[kind]}

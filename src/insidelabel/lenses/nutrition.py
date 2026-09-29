"""
nutrition.py - D-133: the nutrition table, read by the model, judged by rules.

The vision model copies the table as printed (prompt.py rule 10): each row's
label and cells, the serving size and the servings per pack. It never computes
or converts. Everything else is here, as plain rules over
data/nutrition_panel.json (D-004):

1. Which printed row is which nutrient, in what unit.
2. Which numbers can be trusted. A number is kept only if
   - it appears in the independent reader's text of the same photo (Cloud
     Vision, or Tesseract when Cloud Vision isn't set up, D-093), and
   - the table's own arithmetic agrees with it: the % RDA per serve FSSAI
     requires (L&D 2020 5(3)(b)) fits the per 100 figure and the serving size;
     a printed per serving amount fits the per 100 figure; sugars sit within
     carbohydrate, added sugars within sugars, saturated and trans fat within
     total fat; salt is sodium x 2.5 (WHO); servings x serving size is about
     the net quantity.
   A failed check drops every number it involves. It never guesses which one
   was right: a number we aren't sure of is not shown at all.
3. What is left, with how it was checked. lenses/screen.py words it (D-091).

Nothing here changes a score, a band or a headline (information only, D-133).
"""

import json
import os
import re

from insidelabel.core import engine


def _load(name):
    with open(os.path.join(engine.DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


PANEL = _load("nutrition_panel.json")
THRESHOLDS = _load("nutrition_thresholds.json")
NUTRIENTS = PANEL["nutrients"]
UNIT = {n["key"]: n["unit"] for n in NUTRIENTS if n["key"] != "ignore"}
LABEL = {n["key"]: n["label"] for n in NUTRIENTS if n["key"] != "ignore"}
RDA = {k: v for k, v in PANEL["rda_basis"].items() if not k.startswith("_")}
FAT_KCAL = PANEL["energy_factors"]["fat"]
SALT_PER_SODIUM = THRESHOLDS["salt_per_sodium"]["value"]

STATUSES = ("read", "partial", "not_found", "unreadable")
# What a printed table can still be said to contain after the checks.
SHOWN = ("read", "partial")

_DASHES = "-\u2013\u2014"
_NUM = r"(\d+(?:[.,]\d+)?)"
_MAX = re.compile(r"not\s+more\s+than|\bnmt\b|\bmax(?:imum)?\b|\bupto\b|\bup\s+to\b", re.I)
_LT = re.compile(r"^\s*(?:<|less\s+than)", re.I)
_CELL_UNIT = re.compile(r"^\s*(kcal|kj|mcg|µg|mg|g|ml)\b", re.I)
_LABEL_UNIT = re.compile(r"\(\s*(kcal|kj|mcg|µg|mg|g)\s*\)", re.I)
_AMOUNT = re.compile(_NUM + r"\s*(kg|gms?|grams?|g|ml|litres?|liters?|ltrs?|l)(?![a-z])", re.I)


def _f(printed):
    return float(printed.replace(",", "."))


def nutrient_key(label):
    """The nutrient a printed row label names, "ignore", or None."""
    t = (label or "").lower()
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t)
    t = re.sub(r"\bof which\b", " ", t)
    t = re.sub(r"[^a-z ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for n in NUTRIENTS:
        for name in n["names"]:
            if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", t):
                return n["key"]
    return None


def _unit_of(cell_rest, unit_col, label):
    for text, pat in ((cell_rest, _CELL_UNIT), (unit_col or "", _CELL_UNIT), (label or "", _LABEL_UNIT)):
        m = pat.search(text) if pat is _LABEL_UNIT else pat.match(text)
        if m:
            u = m.group(1).lower()
            return "mcg" if u == "µg" else u
    return None


def _to_canonical(value, unit, key):
    want = UNIT[key]
    if unit is None or unit == want:
        return value
    if key == "energy":
        return None                      # kJ only: we read kcal, never convert
    scale = {("g", "mg"): 1000.0, ("mg", "g"): 0.001}
    return value * scale[(unit, want)] if (unit, want) in scale else None


def read_cell(cell, key, label=None, unit_col=None):
    """A printed cell as {value, unit, printed, bound}, or None ("-", blank, kJ only)."""
    s = ("" if cell is None else str(cell)).strip()
    if not s or all(c in _DASHES + " " for c in s):
        return None
    m = unit = None
    if key == "energy":
        # "1884 kJ / 450 kcal": the kcal figure. A kJ-only cell isn't read (never converted).
        m = re.search(r"(?<![\d.])" + _NUM + r"\s*k\s?cal", s, re.I)
        unit = "kcal" if m else None
        if m is None and re.search(r"k\s?j", s, re.I) and _unit_of("", unit_col, label) != "kcal":
            return None
    m = m or re.search(r"(?<![\d.])" + _NUM, s)
    if m is None:
        return None
    printed = m.group(1)
    unit = unit or _unit_of(s[m.end():], unit_col, label)
    value = _to_canonical(_f(printed), unit, key)
    if value is None:
        return None
    bound = "lt" if _LT.search(s) else ("max" if _MAX.search(s) or _MAX.search(label or "") else None)
    return {"value": value, "unit": UNIT[key], "printed": printed, "bound": bound}


def _percent(cell):
    s = ("" if cell is None else str(cell)).strip()
    m = re.search(r"(?<![\d.])" + _NUM, s)
    return (_f(m.group(1)), m.group(1)) if m else None


def amount(text):
    """'12g', '200 ml', '1 croissant (45 g)', '2.25 L' -> (value in g or ml, 'g' | 'ml', printed digits)."""
    m = _AMOUNT.search(text or "")
    if not m:
        return None
    v, u = _f(m.group(1)), m.group(2).lower()
    if u == "kg":
        return v * 1000, "g", m.group(1)
    if u.startswith("l"):
        return v * 1000, "ml", m.group(1)
    return v, ("ml" if u == "ml" else "g"), m.group(1)


def form_of(basis_text):
    """'Per 100 g' -> 'solid', 'PER 100ml' -> 'liquid'; anything not per 100 -> None."""
    a = amount(basis_text)
    if not a or a[0] != 100:
        return None
    return "liquid" if a[1] == "ml" else "solid"


def ocr_numbers(text):
    """Every number in the independent reader's text, as floats ('22,24' reads as 22.24)."""
    t = re.sub(r"(?<=\d),(?=\d)", ".", text or "")
    return {float(m.group(1)) for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)(?!\d)", t)}


def numbers(raw):
    """{nutrient: value per 100} as transcribed, before any check. For measuring the reader (eval)."""
    out = {}
    for r in (raw or {}).get("rows") or []:
        key = nutrient_key(r.get("nutrient"))
        if key in (None, "ignore") or key in out:
            continue
        c = read_cell(r.get("per_100"), key, r.get("nutrient"), r.get("unit"))
        if c:
            out[key] = c["value"]
    return out


def _near(a, b, rel, floor):
    return abs(a - b) <= max(floor, rel * abs(b))


def _floor(key):
    return 1.0 if UNIT[key] in ("kcal", "mg") else 0.1


def check(raw, ocr_text, net_quantity=None, reader=None):
    """
    raw: the model's `nutrition` object (prompt.py), or None for an answer that
    predates D-133. ocr_text: the independent reader's text of the same photo.
    Returns the checked table:
      status   not_read (older answer) | missing (no table in the photo) |
               unclear (a table, nothing usable) | unverified (no second reading) |
               read | partial (some numbers dropped)
      form     solid | liquid       basis  '100 g' | '100 ml'
      serving  {value, unit, printed} or None      servings  float or None
      values   {nutrient: {value, unit, printed, bound, label}}
      dropped  [{key, reason}]      table  the rows as transcribed (for reviewers)
    """
    if not isinstance(raw, dict):
        return {"status": "not_read"}
    status = raw.get("status") if raw.get("status") in STATUSES else "unreadable"
    if status == "not_found":
        return {"status": "missing"}
    base = {"table": raw, "reader": reader, "dropped": [], "values": {}, "serving": None, "servings": None}
    rows = raw.get("rows") if isinstance(raw.get("rows"), list) else []
    form = form_of(raw.get("per_100_basis"))
    if status == "unreadable" or not rows:
        return {**base, "status": "unclear"}
    if form is None:
        return {**base, "status": "unclear", "dropped": [{"key": "*", "reason": "the table isn't per 100 g or 100 ml"}]}
    base.update(form=form, basis="100 ml" if form == "liquid" else "100 g")

    values, rda, per_serving = {}, {}, {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = nutrient_key(r.get("nutrient"))
        if key in (None, "ignore") or key in values:
            continue
        c = read_cell(r.get("per_100"), key, r.get("nutrient"), r.get("unit"))
        if c is None:
            continue
        values[key] = {**c, "label": r.get("nutrient")}
        pct = _percent(r.get("rda_percent"))
        if pct:
            rda[key] = pct
        ps = read_cell(r.get("per_serving"), key, r.get("nutrient"), r.get("unit"))
        if ps:
            per_serving[key] = ps
    serving = amount(raw.get("serving_size"))
    servings = _percent(raw.get("servings_per_pack"))
    dropped = []

    def drop(keys, reason):
        for k in keys:
            if k in values:
                del values[k]
                dropped.append({"key": k, "reason": reason})

    # 1. Every number must be in the second reading of the same photo.
    if not (ocr_text or "").strip():
        return {**base, "status": "unverified",
                "dropped": [{"key": k, "reason": "no second reading of the photo"} for k in values]}
    seen = ocr_numbers(ocr_text)
    drop([k for k, v in values.items() if _f(v["printed"]) not in seen], "not in the second reading")
    rda = {k: p for k, p in rda.items() if p[0] in seen}
    per_serving = {k: p for k, p in per_serving.items() if _f(p["printed"]) in seen}
    if serving and _f(serving[2]) not in seen:
        dropped.append({"key": "serving", "reason": "not in the second reading"})
        serving = None
    if servings and servings[0] not in seen:
        servings = None

    # 2. The per serve columns against the per 100 column. When most disagree, the
    #    serving size is the misread number; when one does, that row is.
    rda_per_100 = "100" in (raw.get("rda_column") or "")
    size = 100.0 if rda_per_100 else (serving[0] if serving else None)
    if size:
        bad, n = [], 0
        for k, (pct, _p) in rda.items():
            if k in RDA and k in values:
                n += 1
                if not _near(pct, values[k]["value"] * size / 100 / RDA[k] * 100, 0.06, 0.1):
                    bad.append(k)
        for k, ps in per_serving.items():
            if k in values and serving:
                n += 1
                if not _near(ps["value"], values[k]["value"] * serving[0] / 100, 0.08, _floor(k)):
                    bad.append(k)
        bad = list(dict.fromkeys(bad))
        if not rda_per_100 and serving and len(bad) >= 2 and len(bad) * 2 > n:
            dropped.append({"key": "serving", "reason": "the per serve column doesn't fit it"})
            serving = servings = None
        else:
            drop(bad, "the per serve column doesn't fit it")

    # 3. Parts within wholes.
    for part, whole in (("total_sugars", "carbohydrate"), ("added_sugars", "total_sugars"),
                        ("saturated_fat", "total_fat"), ("trans_fat", "total_fat")):
        if part in values and whole in values:
            if values[part]["value"] > values[whole]["value"] + max(0.05, 0.01 * values[whole]["value"]):
                drop([part, whole], f"{part} is more than {whole}")
    if all(k in values for k in ("saturated_fat", "trans_fat", "total_fat")):
        if values["saturated_fat"]["value"] + values["trans_fat"]["value"] > values["total_fat"]["value"] + 0.1:
            drop(["saturated_fat", "trans_fat", "total_fat"], "saturated and trans fat add up to more than total fat")

    # 4. Salt is sodium x 2.5 (WHO: 1 g of salt is 400 mg of sodium).
    if "salt" in values and "sodium" in values:
        if not _near(values["salt"]["value"] * 1000, values["sodium"]["value"] * SALT_PER_SODIUM, 0.1, 50):
            drop(["salt", "sodium"], "salt and sodium don't agree")

    # 5. Servings x serving size is about the net quantity, when all three are known.
    net = amount(net_quantity)
    if serving and servings and net and net[1] == serving[1]:
        if not _near(serving[0] * servings[0], net[0], 0.05, 1):
            dropped.append({"key": "serving", "reason": "servings x serving size isn't the net quantity"})
            serving = servings = None

    base.update(values=values, dropped=dropped,
                serving=({"value": serving[0], "unit": serving[1], "printed": serving[2]} if serving else None),
                servings=servings[0] if servings else None)
    if not values:
        return {**base, "status": "unclear"}
    lost = any(d["key"] != "serving" for d in dropped)
    return {**base, "status": "partial" if lost or status == "partial" else "read"}


def not_in_text(panel, ocr_text):
    """
    The panel's numbers that aren't in `ocr_text` (review checker, D-117): a
    reviewer-facing list, empty when there is nothing to check.
    """
    values = (panel or {}).get("values") or {}
    if not values:
        return []
    seen = ocr_numbers(ocr_text)
    out = [f"{LABEL.get(k, k)} {v['printed']}" for k, v in values.items() if _f(v["printed"]) not in seen]
    s = (panel or {}).get("serving")
    if s and _f(s["printed"]) not in seen:
        out.append(f"serving size {s['printed']}")
    return out


def public(panel):
    """The checked table for API readers: without the raw transcription. None when not read."""
    if not panel or panel.get("status") in (None, "not_read"):
        return None
    return {k: v for k, v in panel.items() if k != "table"}


def accuracy(gold, pred):
    """
    How well a reading copied a gold table: (right, total), or None when the
    reading has no table at all (an answer from before D-133, not measurable).
    Every per 100 number and the serving size count once; a gold label with no
    readable table counts its status once ("not_found", "unreadable").
    """
    if not isinstance(pred, dict):
        return None
    gold = gold or {}
    g, p = numbers(gold), numbers(pred)
    if not g:
        return (int(pred.get("status") == gold.get("status")), 1)
    right = sum(1 for k, v in g.items() if k in p and abs(p[k] - v) < 1e-9)
    gs, ps = amount(gold.get("serving_size")), amount(pred.get("serving_size"))
    total = len(g) + (1 if gs else 0)
    right += 1 if gs and ps and gs[:2] == ps[:2] else 0
    return right, total

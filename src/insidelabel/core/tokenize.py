"""Ingredient tokenization and INS/E-number extraction."""

import json
import os
import re


DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
)


def _load_normalization():
    with open(
        os.path.join(DATA_DIR, "normalization.json"),
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


NORM = _load_normalization()

_CLASS_WORDS = NORM.get("additive_class_words", {}).get("words", [
    "emulsifier", "emulsifiers", "preservative", "preservatives",
    "stabiliser", "stabilisers", "stabilizer", "stabilizers",
    "acidity regulator", "acidity regulators", "raising agent",
    "raising agents", "colour", "colours", "color", "colors",
    "flavour enhancer", "flavour enhancers", "sweetener", "sweeteners",
    "antioxidant", "antioxidants", "thickener", "thickeners",
])

_CLASS_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(
        re.escape(w).replace(r"\ ", r"\s+")
        for w in sorted(_CLASS_WORDS, key=len, reverse=True)
    ) + r")(?![a-z])",
    re.IGNORECASE,
)

# INS numbers run 100-1521, so 3 or 4 digits, plus an optional single-letter
# suffix (150d, 472e). The suffix must not run into more letters, so "250gm"
# is not "250g". A spaced suffix ("160 a(ii)", as Maliban prints it) is
# accepted for a-f only, so "503 i" or "322 and" are never read as suffixes.
# Every INS pattern in the codebase is built from this one.
INS_NUMBER = r"(\d{3,4}(?:[a-z](?![a-z])|\s[a-f](?![a-z]))?)(?![0-9])"

# A bare additive number, not already carrying an INS/E prefix.
_BARE_NUM = re.compile(
    r"(?<![a-z0-9])(?<!ins )(?<!ins)(?<!e)" + INS_NUMBER,
    re.IGNORECASE,
)

# An explicit INS/E number. The prefix must be a word of its own: without the
# lookbehind, "tomato paste 250 g" reads as "e 250" (sodium nitrite) and
# "raisins 150g" as "ins 150g".
INS_RE = re.compile(r"(?<![a-z])(?:ins|e)[\s\-.]*?" + INS_NUMBER, re.IGNORECASE)

# A token that is nothing but an additive number. Suffix limited to a-f so a
# quantity like "150g" left on its own is not read as an INS number.
_WHOLE_NUM = re.compile(r"(\d{3,4}[a-f]?)")


_OPEN = "([{"
_CLOSE = {"(": ")", "[": "]", "{": "}"}


def _balanced_span(text, open_idx):
    """Return the index just past the bracket group opening at open_idx.

    Handles (), [] and {}: real labels print "HUMECTANT [420(ii)]" and
    "MIX {EMULSIFIERS [481(i) & 471]}" as often as round brackets.
    """
    opener = text[open_idx]
    closer = _CLOSE[opener]
    depth = 0

    for i in range(open_idx, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i + 1

    return None


def prefix_bare_ins(raw):
    """
    Rewrite bare additive numbers as explicit INS numbers, but ONLY inside a
    bracket introduced by an additive class word.
    """
    out = []
    pos = 0

    for m in _CLASS_RE.finditer(raw):
        if m.start() < pos:
            continue

        j = m.end()

        while j < len(raw) and raw[j] in " \t:.-":
            j += 1

        if j >= len(raw) or raw[j] not in _OPEN:
            continue

        end = _balanced_span(raw, j)

        if end is None:
            continue

        inner = raw[j + 1:end - 1]

        if not re.search(r"\d{3}", inner):
            continue

        out.append(raw[pos:j + 1])
        out.append(_BARE_NUM.sub(r"INS \1", inner))
        pos = end - 1

    out.append(raw[pos:])
    return "".join(out)


def tokenize(raw):
    """Split a raw ingredient string into candidate ingredient tokens."""

    raw = re.sub(r"(?i)\ballergen[s]?\b.*$", "", raw)
    raw = prefix_bare_ins(raw)

    # A spaced "&" separates entries: "PRESERVATIVES (282 & 202)". An
    # unspaced one is part of a name ("fd&c yellow 5") and is left alone.
    # A full stop ends an entry, but not a decimal point between two digits:
    # "58.3%" and "0.504g" are amounts, and splitting them left fragments such
    # as "wheat flour 58" that D-115 would show as the label's words.
    parts = re.split(r"[,;\n]|(?<!\d)\.|\.(?!\d)|\s+&\s+", raw)
    tokens = []

    for p in parts:
        inner = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", p)
        base = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", p)

        for chunk in [base] + inner:
            for sub in re.split(r"[,;]|\s+&\s+", chunk):
                t = sub.strip().lower()
                t = re.sub(r"\s+", " ", t)

                if t and not re.fullmatch(r"[\d\s%.]+", t):
                    tokens.append(t)

    return tokens


def extract_ins(token):
    """If token contains an INS/E number, return the bare number string."""

    m = INS_RE.search(token)

    if m:
        return m.group(1).lower().replace(" ", "")

    m2 = _WHOLE_NUM.fullmatch(token.strip())

    if m2:
        return m2.group(1).lower()

    return None


def ins_numbers(text):
    """
    Every INS number the engine would read in `text` (a string, or a list of
    ingredient entries, joined as /scan joins them). The one way to ask "which
    additive numbers are in this?" anywhere in the code (D-099).
    """
    if not isinstance(text, str):
        text = ", ".join(text or [])
    return {i for i in (extract_ins(t) for t in tokenize(text)) if i}

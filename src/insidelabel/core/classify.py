"""Ingredient classification and NOVA marker detection."""

import re


def _inside(alias, token):
    """
    The alias inside a longer entry ("vegetable shortening" has "shortening"),
    but not negated: "non-hydrogenated fat" is not hydrogenated fat (D-135). An
    alias that itself starts with "non-" ("non-nutritive sweetener") still matches.
    """
    return re.search(r"(?<!non-)(?<!non )" + re.escape(alias), token) is not None


def _nova_marker(token, canonical, nova_lookup):
    for key in (token, canonical):
        if key in nova_lookup:
            return nova_lookup[key]

    for al, marker in nova_lookup.items():
        if _inside(al, token):
            return marker

    return None


def _is_nova(token, canonical, nova_lookup):
    return _nova_marker(token, canonical, nova_lookup) is not None


def _label_term(token, marker):
    """
    D-115: the words to show for a marker, always words on the pack. The token
    as read when it is a whole term; for a fragment such as "flavours (natural",
    the longest of the row's own known names found inside it. Never the row's
    name, which is a category ("Added flavour (natural/artificial/...)") and
    would put words on the screen that the label doesn't say.
    """
    if not any(ch in token for ch in "()[]{}"):
        return token
    inside = [al.lower() for al in marker["aliases"] if al.lower() in token]
    return max(inside, key=len) if inside else token


def classify_token(
    token,
    synonym_lookup,
    additive_by_ins,
    nova_lookup,
):
    """Return a flag dict for a token, or None if unremarkable."""

    canonical = (
        synonym_lookup[token]
        if token in synonym_lookup
        else token
    )

    # Local import avoids making tokenize part of the classification layer.
    from .tokenize import extract_ins

    ins = extract_ins(token)

    if ins and ins in additive_by_ins:
        a = additive_by_ins[ins]

        return {
            "ingredient": token,
            "matched_as": f"INS {ins} ({a['name']})",
            "type": "additive",
            "concern": a["concern"],
            "why": a["why"],
            "sources": a["sources"],
            "flags": a.get("flags", []),
            "verify": a.get("verify", False),
            "nova_group4": _is_nova(token, canonical, nova_lookup),
        }

    for a in additive_by_ins.values():
        name_l = a["name"].lower()

        if (
            canonical == name_l
            or token == name_l
            or canonical in name_l.split(" (")
        ):
            return {
                "ingredient": token,
                "matched_as": f"{a['name']} (INS {a['ins']})",
                "type": "additive",
                "concern": a["concern"],
                "why": a["why"],
                "sources": a["sources"],
                "flags": a.get("flags", []),
                "verify": a.get("verify", False),
                "nova_group4": _is_nova(token, canonical, nova_lookup),
            }

    marker = _nova_marker(token, canonical, nova_lookup)

    if marker:
        return {
            "ingredient": token,
            "matched_as": f"NOVA marker: {marker['name']}",
            "label_term": _label_term(token, marker),
            "type": "nova_marker",
            "concern": (
                "moderate"
                if marker["category"] != "cosmetic_additive"
                else "low"
            ),
            "why": (
                f"Ultra-processing marker "
                f"({marker['category'].replace('_', ' ')}). "
                f"Rarely used in home cooking; signals industrial formulation."
            ),
            "sources": ["NOVA"],
            "flags": [
                "nova_group4_marker",
                marker["category"],
            ],
            "verify": False,
            "nova_group4": True,
        }

    return None


# Compatibility helpers for the engine's internal calls.
# These are configured by engine.py when needed.
def make_nova_helpers(nova_lookup):
    def marker(token, canonical):
        return _nova_marker(token, canonical, nova_lookup)

    def is_nova(token, canonical):
        return _is_nova(token, canonical, nova_lookup)

    return marker, is_nova

"""Ingredient classification and NOVA marker detection."""


def _nova_marker(token, canonical, nova_lookup):
    for key in (token, canonical):
        if key in nova_lookup:
            return nova_lookup[key]

    for al, marker in nova_lookup.items():
        if al in token:
            return marker

    return None


def _is_nova(token, canonical, nova_lookup):
    return _nova_marker(token, canonical, nova_lookup) is not None


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

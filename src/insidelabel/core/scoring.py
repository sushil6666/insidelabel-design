"""Score and grade helpers."""

GRADE_BANDS = [
    (85, "A", "clean"),
    (70, "B", "clean"),
    (50, "C", "mixed"),
    (30, "D", "ultra-processed"),
    (0, "E", "ultra-processed"),
]

CONCERN_PENALTY = {
    "none": 0,
    "low": 4,
    "moderate": 12,
    "high": 25,
}


def grade_for(score):
    for threshold, letter, band in GRADE_BANDS:
        if score >= threshold:
            return letter, band

    return "E", "ultra-processed"

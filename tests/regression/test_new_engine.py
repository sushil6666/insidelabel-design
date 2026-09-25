import sys

sys.path.insert(0, "src")

from insidelabel.core import engine


LIMCA = (
    "CARBONATED WATER, SUGAR, ACIDITY REGULATORS (330, 331(iii)), "
    "STABILIZERS (414,471), PRESERVATIVE (211), "
    "FLAVOURS (NATURAL, NATURE-IDENTICAL & ARTIFICIAL (LEMON) "
    "FLAVOURING SUBSTANCES)"
)

result = engine.analyze(LIMCA)

assert result["binary"] == "ultra-processed"
assert result["grade"] == "B"
# 80 since 2026-09-25: INS 414 (gum arabic) is low with no concern flag, so
# it scores 0 (additives.json _meta.scoring). Was 76.
assert result["score"] == 80

print("NEW PACKAGE ENGINE: PASS")
print("binary:", result["binary"])
print("grade:", result["grade"])
print("score:", result["score"])

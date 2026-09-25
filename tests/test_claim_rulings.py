"""
Claim rulings decided by a person, pinned so a new rule can't overturn them (D-054).

Each case is a real label, transcribed from the pack. A future rule that makes
one of these produce a finding has to change the decision first.
"""
from insidelabel.claims import checker
from insidelabel.core import engine

# Patanjali Doodh Biscuits, as published after review on 2026-09-25.
DOODH = ["Wheat Flour (Atta) 58.3%", "Sugar", "Edible vegetable oil (Palm oil)",
         "Milk products (3.56%) [Sweetened condensed milk, Cow's milk solid, Ghee, Cheese]",
         "Liquid glucose", "Invert syrup", "Iodized salt",
         "Raising agent [INS 500(ii), INS 503(ii), INS 341(i)]", "Natural",
         "Nature Identical & Artificial Flavours (Milk & Vanilla)", "Emulsifier [INS 322(i)]",
         "Dough conditioner (INS 223)"]


def test_100_percent_atta_says_nothing_when_atta_is_the_only_flour():   # D-054
    raw = ", ".join(DOODH)
    r = checker.check_claims(["100% ATTA"], raw, engine.analyze(raw), "read")
    assert not any(c["contradicted"] for c in r.get("checked", []))
    assert r.get("unmatched_claims") == ["100% ATTA"]        # stored as printed, no rule applied

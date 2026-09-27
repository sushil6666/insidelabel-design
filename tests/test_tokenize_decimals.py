"""
A decimal point is part of an amount, not the end of an entry.

The tokenizer split on every ".", so "Wheat flour (Atta) 58.3%" became
"wheat flour 58" + "atta", and "Natural Mint Flavour 0.010g" (the first pack
scanned on the live site, 2026-09-27) became "natural mint flavour 0". Since
D-115 shows a marker in the label's words, such a fragment could reach the
headline. A full stop between entries still splits. Labels are invented or
copied from the gold set.
"""
import json

import pytest
from fastapi.testclient import TestClient

from insidelabel.api.main import app
from insidelabel.core import engine
from insidelabel.core.tokenize import ins_numbers, tokenize


def test_amounts_stay_whole():
    assert tokenize("Wheat flour (Atta) 58.3%, Sugar") == ["wheat flour 58.3%", "atta", "sugar"]
    assert tokenize("Natural Mint Flavour 0.010g") == ["natural mint flavour 0.010g"]
    assert tokenize("*Rama Tulsi leaf powder (Ocimum sanctum) 0.504g") == [
        "*rama tulsi leaf powder 0.504g", "ocimum sanctum"]


def test_a_bracketed_percentage_is_dropped_not_split():
    assert tokenize("Milk solids (3.6%), Cocoa solids (1.02%)") == ["milk solids", "cocoa solids"]


def test_a_full_stop_between_entries_still_splits():
    assert tokenize("Sugar. Salt") == ["sugar", "salt"]
    assert tokenize("Flavour 0.5g. Salt") == ["flavour 0.5g", "salt"]
    assert tokenize("Contains 2.5% salt.") == ["contains 2.5% salt"]


def test_ins_numbers_unchanged_by_amounts():
    with_amounts = "Emulsifier (INS 322(i)) 0.5%, Preservative (INS 211) 0.02%, Colour (INS 150d) 1.5%"
    without = "Emulsifier (INS 322(i)), Preservative (INS 211), Colour (INS 150d)"
    assert ins_numbers(with_amounts) == ins_numbers(without)
    assert {"211", "150d"} <= ins_numbers(with_amounts)


def test_the_tulsi_headline_has_no_fragment():
    c = TestClient(app)
    ing = ["*Rama Tulsi leaf powder (Ocimum sanctum) 0.504g", "*Peppermint leaf powder (Mentha piperita) 0.076g",
           "Natural Mint Flavour 0.010g"]
    v = {"front_status": "not_provided", "back_status": "read", "ingredients_status": "read",
         "product": {"brand": None, "name": None, "variant": None, "net_quantity": None, "veg_mark": "veg"},
         "product_match": {"status": "single_image", "evidence": []}, "front_identity": None,
         "back_identity": {"brand": None, "name": None, "manufacturer": None, "fssai_licence": None},
         "ingredient_lines": [", ".join(ing)], "ingredient_count": len(ing), "ingredients": ing,
         "allergen_statement": None, "front_claims": [], "front_claim_footnotes": [], "extraction_notes": [],
         "confidence": {"ingredients": 0.98, "front_claims": 0.0, "product_identity": 0.5}}
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c63f8cfc0f00f0004850180848c9921"
                        "0000000049454e44ae426082")
    r = c.post("/scan", files={"back": ("b.png", png, "image/png")}, data={"replay": json.dumps(v)})
    assert r.status_code == 200, r.text
    head = r.json()["screen"]["headline"]["text"]
    assert head == "Made with industrial ingredients, such as natural mint flavour 0.010g."


def _same_judgement(a_text, b_text):
    a, b = engine.analyze(a_text), engine.analyze(b_text)
    for k in ("band", "binary", "score", "nova_ultra_processed"):
        assert a.get(k) == b.get(k), k
    assert sorted(f["matched_as"] for f in a["flags"]) == sorted(f["matched_as"] for f in b["flags"])


def test_a_bracketed_amount_never_changes_a_judgement():
    _same_judgement("Wheat flour (Atta) (58.3%), Sugar (25.5%), Milk solids (3.6%), Liquid glucose (4.2%), "
                    "Emulsifier (INS 471) (0.5%)",
                    "Wheat flour (Atta), Sugar, Milk solids, Liquid glucose, Emulsifier (INS 471)")


@pytest.mark.xfail(strict=True, reason=(
    "Known, older than this fix: an amount after a name without brackets ('Sugar 25.5%') stops the "
    "exact match, so the sugar isn't counted (score 88, not 80). Fixing it changes judgements on real "
    "packs; it needs its own check against the gold set (STATE.md §8)."))
def test_an_unbracketed_amount_never_changes_a_judgement():
    _same_judgement("Sugar 25.5%, Liquid glucose 4.2%", "Sugar, Liquid glucose")

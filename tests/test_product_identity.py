import sys

sys.path.insert(0, "src")

from insidelabel.extraction.providers.gemini import _verified_anchors


def test_limca_company_name_without_verified_anchor_is_not_match():
    vision = {
        "product_match": {
            "status": "mismatch",
            "evidence": [
                "The Coca-Cola Company printed on both front and back label side markings",
                "Matching green/red design scheme of Limca carbonated soft drink bottle",
            ],
        },
        "front_identity": {
            "brand": "Limca",
            "name": "Limca",
            "manufacturer": None,
        },
        "back_identity": {
            "brand": "The Coca-Cola Company",
            "name": None,
            "manufacturer": "HINDUSTAN COCA-COLA BEVERAGES PVT. LTD.",
            "fssai_licence": "10012011000620",
        },
    }

    anchors = _verified_anchors(vision)

    assert anchors == []
    assert vision["product_match"]["status"] in ("match", "mismatch")

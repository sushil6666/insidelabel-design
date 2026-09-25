"""Request / response models. The engine verdict passes through unchanged."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    raw_ingredients: str = Field(
        ...,
        min_length=1,
        description="Raw ingredient list text, as printed on the label.",
        json_schema_extra={
            "example": "Refined wheat flour (maida), Sugar, Palm oil, "
                       "Emulsifiers (INS 322, INS 471), INS 621"
        },
    )
    compare_regulators: bool = Field(
        False,
        description="Also return how the EU and US treat each additive. Information only; "
                    "the verdict always uses FSSAI rules.",
    )


class ClaimCheckRequest(BaseModel):
    raw_ingredients: str = Field(..., min_length=1)
    front_claims: List[str] = Field(default_factory=list)
    front_status: str = Field(
        "read",
        description='"read" | "not_provided" | "unreadable"',
    )


class AllergenCheckRequest(BaseModel):
    ingredients: List[str] = Field(
        ..., min_length=1, description="Ingredient entries, in printed order."
    )
    allergen_statement: Optional[str] = Field(
        None, description='The printed "Contains ... / May contain ..." line, if any.'
    )
    avoid: List[str] = Field(
        ..., min_length=1, description="Allergen codes from data/allergens.json."
    )
    who: Optional[str] = Field(
        None, description="Name used in parent text. Stays on the device in the app."
    )


class ComparePack(BaseModel):
    """One scanned pack, as the client already holds it from /scan."""

    id: str
    name: str
    ingredients: List[str] = Field(..., min_length=1)
    allergen_statement: Optional[str] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0, description='/scan confidence["ingredients"].')
    reliable: bool = Field(
        True, description="/scan reliability: verdict_safe_to_display and ingredients_complete."
    )


class CompareRequest(BaseModel):
    packs: List[ComparePack] = Field(..., min_length=2, max_length=4)
    age: str = Field("kid", description='"toddler" | "kid" | "young"')
    avoid: List[str] = Field(default_factory=list)
    who: Optional[str] = None
    strict_may_contain: bool = True


class ReportRequest(BaseModel):
    """D-076 "Report a mistake"."""

    scan_id: Optional[str] = None
    product_version_id: Optional[int] = None
    device_id: Optional[str] = None
    field: str = Field(..., min_length=1, max_length=64,
                       description='What is wrong, e.g. "ingredients", "allergens", "product_name", "claim".')
    proposed_value: Optional[str] = Field(None, max_length=4000)
    note: Optional[str] = Field(None, max_length=2000)


class AnalyzeResponse(BaseModel):
    """
    `verdict` is engine.analyze() output, verbatim. Nothing in this API mutates
    it. Wrapper-level caveats live in sibling fields so the engine's contract
    stays exactly what engine.py documents.
    """

    verdict: Dict[str, Any]
    engine_version: str
    regulators: Optional[Dict[str, Any]] = None


class ClaimCheckResponse(BaseModel):
    verdict: Dict[str, Any]
    claim_check: Dict[str, Any]
    engine_version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    hint: Optional[str] = None

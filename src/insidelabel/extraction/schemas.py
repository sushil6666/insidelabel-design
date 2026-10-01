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
    # D-139, D-140: what the server needs to refuse a pack that can't be compared
    # (an infant food never, a supplement not yet). Older clients send neither: food.
    kind: Optional[str] = Field(None, description='/scan pack_kind.code, e.g. "food", "infant".')
    pack_statements: List[dict] = Field(default_factory=list,
                                        description="/scan extracted.pack_statements, as printed.")


class CompareRequest(BaseModel):
    packs: List[ComparePack] = Field(..., min_length=2, max_length=4)
    age: str = Field("kid", description='"baby" | "toddler" | "kid" | "young"')
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


class JoinRequest(BaseModel):
    """D-102: a tester's invite code, as typed or from their link."""

    code: str = Field(..., max_length=40)
    device_id: str = Field(..., max_length=64)


class AgreeRequest(BaseModel):
    """D-105: this install accepts this version of "Before you start"."""

    device_id: str = Field(..., max_length=64)
    terms_version: str = Field(..., max_length=40)


class ForgetRequest(BaseModel):
    """D-129 "Delete my data": the install id is the only thing that ties data to a person."""

    device_id: str = Field(..., max_length=64)


class FeedbackRequest(BaseModel):
    """D-102 "Send feedback": what a tester thinks. Not a mistake (D-076), not a problem (D-092)."""

    device_id: str = Field(..., max_length=64)
    comment: str = Field(..., max_length=4000)
    rating: Optional[int] = Field(None, ge=1, le=5)
    screen: Optional[str] = Field(None, max_length=40, description="Where it was sent from: home, result…")
    app_version: Optional[str] = Field(None, max_length=40)


class ProblemRequest(BaseModel):
    """D-092 "Report a problem": the app misbehaved. Goes to the developer, not reviewers."""

    kind: str = Field("user", description='"user" (tapped Report a problem) or "auto" (an app crash).')
    device_id: Optional[str] = None
    scan_id: Optional[str] = None
    request_id: Optional[str] = Field(None, max_length=64, description="The request that failed, if known.")
    comment: Optional[str] = Field(None, max_length=2000)
    app_version: Optional[str] = Field(None, max_length=40)
    signature: Optional[str] = Field(None, max_length=200, description="Error kind + place, to group repeats.")
    client: Dict[str, Any] = Field(default_factory=dict, description="Phone, browser, screen, network. No names.")
    events: List[Dict[str, Any]] = Field(default_factory=list, max_length=200,
                                         description="The app's recent trail, oldest first.")


class SendToUsRequest(BaseModel):
    """D-070 "Send it to us": the refused scans of a pack the app couldn't read."""

    device_id: str = Field(..., description="The install that took the photos; /updates reports back to it.")
    scan_ids: List[str] = Field(..., min_length=1, max_length=6,
                                description="scan_id of each refused attempt, oldest first.")


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

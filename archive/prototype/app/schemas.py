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


class ClaimCheckRequest(BaseModel):
    raw_ingredients: str = Field(..., min_length=1)
    front_claims: List[str] = Field(default_factory=list)
    front_status: str = Field(
        "read",
        description='"read" | "not_provided" | "unreadable"',
    )


class AnalyzeResponse(BaseModel):
    """
    `verdict` is engine.analyze() output, verbatim. Nothing in this API mutates
    it. Wrapper-level caveats live in sibling fields so the engine's contract
    stays exactly what engine.py documents.
    """

    verdict: Dict[str, Any]
    engine_version: str


class ClaimCheckResponse(BaseModel):
    verdict: Dict[str, Any]
    claim_check: Dict[str, Any]
    engine_version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    hint: Optional[str] = None

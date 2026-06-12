"""Pydantic models defining the API contract.

These give us automatic request validation (empty inputs are rejected with a
422 before any LLM call is made) and a typed, documented response shape.
"""

from typing import List, Literal
from pydantic import BaseModel, Field, field_validator


class EvaluateRequest(BaseModel):
    source: str = Field(..., description="The raw information the document should be based on.")
    document: str = Field(..., description="The generated document to evaluate.")

    @field_validator("source", "document")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value


class Scores(BaseModel):
    completeness: int = Field(..., ge=1, le=5)
    contextual_utilisation: int = Field(..., ge=1, le=5)
    factual_accuracy: int = Field(..., ge=1, le=5)
    confidence_calibration: int = Field(..., ge=1, le=5)
    consistency: int = Field(..., ge=1, le=5)
    specification_adherence: int = Field(..., ge=1, le=5)


class Flag(BaseModel):
    section: str
    issue: str
    severity: Literal["high", "medium", "low"]


class EvaluateResponse(BaseModel):
    scores: Scores
    overall: float
    flags: List[Flag] = []
    summary: str

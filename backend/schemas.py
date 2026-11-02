"""Pydantic models defining the API contract.

They give automatic request validation (empty or oversized inputs are rejected
with a 422 before any LLM call is made) and a typed, documented response shape.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_CHARS = int(os.getenv("MAX_INPUT_CHARS", "30000"))

DIMENSIONS = (
    "completeness",
    "contextual_utilisation",
    "factual_accuracy",
    "confidence_calibration",
    "consistency",
    "specification_adherence",
)


class EvaluateRequest(BaseModel):
    source: str = Field(..., description="The raw information the document should be based on.")
    document: str = Field(..., description="The generated document to evaluate.")

    @field_validator("source", "document")
    @classmethod
    def not_blank_or_huge(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        if len(value) > MAX_CHARS:
            raise ValueError(f"must be at most {MAX_CHARS} characters")
        return value


class ConsistencyRequest(EvaluateRequest):
    runs: int = Field(3, ge=2, le=5, description="How many independent evaluations to run.")


class Scores(BaseModel):
    completeness: int = Field(..., ge=1, le=5)
    contextual_utilisation: int = Field(..., ge=1, le=5)
    factual_accuracy: int = Field(..., ge=1, le=5)
    confidence_calibration: int = Field(..., ge=1, le=5)
    consistency: int = Field(..., ge=1, le=5)
    specification_adherence: int = Field(..., ge=1, le=5)

    def mean(self) -> float:
        return round(sum(getattr(self, d) for d in DIMENSIONS) / len(DIMENSIONS), 2)


class Flag(BaseModel):
    section: str
    issue: str
    severity: Literal["high", "medium", "low"]


class Meta(BaseModel):
    model: str | None = None
    latency_ms: float
    attempts: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class EvaluateResponse(BaseModel):
    scores: Scores
    overall: float = Field(
        0.0, description="Mean of the six scores, computed by the server (never trusted from the model)."
    )
    flags: list[Flag] = []
    summary: str
    meta: Meta | None = None

    @model_validator(mode="after")
    def compute_overall(self) -> EvaluateResponse:
        self.overall = self.scores.mean()
        return self


class DimensionSpread(BaseModel):
    mean: float
    min: int
    max: int
    spread: int


class ConsistencyResponse(BaseModel):
    runs: int
    stable: bool = Field(..., description="True when no dimension moved by more than 1 point between runs.")
    dimensions: dict[str, DimensionSpread]
    overall_mean: float
    evaluations: list[EvaluateResponse]


class ExtractResponse(BaseModel):
    filename: str
    characters: int
    text: str

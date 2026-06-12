"""Schema validation tests: empty input must be rejected before any LLM call."""

import pytest
from pydantic import ValidationError

from schemas import EvaluateRequest, EvaluateResponse


def test_valid_request():
    req = EvaluateRequest(source="my transcript", document="my cv")
    assert req.source == "my transcript"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
def test_blank_source_rejected(bad):
    with pytest.raises(ValidationError):
        EvaluateRequest(source=bad, document="something")


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_document_rejected(bad):
    with pytest.raises(ValidationError):
        EvaluateRequest(source="something", document=bad)


def test_scores_out_of_range_rejected():
    payload = {
        "scores": {
            "completeness": 6,  # invalid: > 5
            "contextual_utilisation": 5,
            "factual_accuracy": 5,
            "confidence_calibration": 5,
            "consistency": 5,
            "specification_adherence": 5,
        },
        "overall": 5.0,
        "flags": [],
        "summary": "ok",
    }
    with pytest.raises(ValidationError):
        EvaluateResponse(**payload)

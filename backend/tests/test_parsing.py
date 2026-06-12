"""Parsing tests: the model rarely returns perfectly clean JSON. These cover
the realistic cases - fenced JSON, surrounding prose, and unrecoverable junk
with a successful retry."""

import pytest

from evaluator import EvaluationError, evaluate

VALID_JSON = """{
  "scores": {
    "completeness": 4, "contextual_utilisation": 5, "factual_accuracy": 5,
    "confidence_calibration": 3, "consistency": 4, "specification_adherence": 5
  },
  "overall": 4.33,
  "flags": [{"section": "Contact", "issue": "Phone number not in source", "severity": "high"}],
  "summary": "Strong use of source but one fabricated contact detail."
}"""


class StubClient:
    """Returns a queued list of canned responses, one per call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self._responses.pop(0)


def test_parses_clean_json():
    client = StubClient([VALID_JSON])
    result = evaluate("source", "document", client)
    assert result.scores.completeness == 4
    assert result.flags[0].severity == "high"
    assert client.calls == 1


def test_parses_json_wrapped_in_fences():
    client = StubClient(["```json\n" + VALID_JSON + "\n```"])
    result = evaluate("source", "document", client)
    assert result.overall == pytest.approx(4.33)


def test_parses_json_with_surrounding_prose():
    noisy = "Sure! Here is the evaluation:\n" + VALID_JSON + "\nHope that helps."
    client = StubClient([noisy])
    result = evaluate("source", "document", client)
    assert result.scores.factual_accuracy == 5


def test_retries_once_then_succeeds():
    client = StubClient(["this is not json at all", VALID_JSON])
    result = evaluate("source", "document", client)
    assert client.calls == 2
    assert result.summary.startswith("Strong use")


def test_raises_after_two_bad_responses():
    client = StubClient(["garbage", "still garbage"])
    with pytest.raises(EvaluationError):
        evaluate("source", "document", client)
    assert client.calls == 2

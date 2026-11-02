"""The consistency mode runs the judge several times and reports score spread."""

import json

import pytest

from evaluator import evaluate_consistency


def _reply(**overrides):
    scores = {
        "completeness": 4,
        "contextual_utilisation": 5,
        "factual_accuracy": 5,
        "confidence_calibration": 3,
        "consistency": 4,
        "specification_adherence": 5,
    }
    scores.update(overrides)
    return json.dumps({"scores": scores, "flags": [], "summary": "ok"})


class Queue:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def test_stable_when_runs_agree_within_one_point():
    out = evaluate_consistency("s", "d", Queue([_reply(), _reply(factual_accuracy=4), _reply()]), runs=3)
    assert out.stable is True
    assert out.dimensions["factual_accuracy"].spread == 1
    assert out.dimensions["factual_accuracy"].mean == pytest.approx(4.67)
    assert len(out.evaluations) == 3


def test_unstable_when_a_dimension_swings_two_points():
    out = evaluate_consistency("s", "d", Queue([_reply(), _reply(confidence_calibration=1)]), runs=2)
    assert out.stable is False
    assert out.dimensions["confidence_calibration"].spread == 2

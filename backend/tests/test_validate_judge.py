"""The judge-validation script converts ResuMetric verdicts for sixdim-eval agreement metrics."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("sixdim_eval")

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("validate_judge", ROOT / "eval" / "validate_judge.py")
validate_judge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_judge)


class Fake:
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def _reply(fa):
    scores = dict.fromkeys(validate_judge.DIMENSIONS, 5)
    scores["factual_accuracy"] = fa
    return json.dumps({"scores": scores, "flags": [], "summary": "s"})


def test_judge_cases_and_agreement():
    from sixdim_eval import judge_agreement
    from sixdim_eval.io import read_cases

    cases = read_cases(ROOT / "eval" / "labelled_cases.example.jsonl")
    replies = [_reply(5), _reply(5), "junk", "junk"]  # third case fails twice -> skipped, not crashed
    evaluations, failed = validate_judge.judge_cases(cases, Fake(replies))
    assert len(evaluations) == 2 and failed == [cases[2].id]

    rows = {r.dimension: r for r in judge_agreement(cases, evaluations)}
    fa = rows["factual_accuracy"]
    assert fa.n == 2
    assert fa.tnr == 0.0  # the human-failed fabricated CV was passed by this (fake) judge

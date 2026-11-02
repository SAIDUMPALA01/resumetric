"""Measure how well ResuMetric's LLM judge agrees with human labels.

    pip install -r backend/requirements-dev.txt
    export ANTHROPIC_API_KEY=...
    python eval/validate_judge.py eval/my_labelled_cases.jsonl

Input: JSON Lines in the sixdim-eval format, one case per line:
    {"id": "cv-01", "source": "...", "output": "<the generated CV>", "human": {"factual_accuracy": 2, ...}}

Output: per-dimension agreement (exact, within-1, quadratic kappa, TPR/TNR)
and eval/results-<model>.jsonl with every judge verdict for error analysis.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sixdim_eval import Case, Evaluation, judge_agreement  # noqa: E402
from sixdim_eval.io import read_cases, write_results  # noqa: E402
from sixdim_eval.report import agreement_markdown  # noqa: E402

from evaluator import EvaluationError, LLMClient, evaluate  # noqa: E402
from schemas import DIMENSIONS  # noqa: E402


def judge_cases(cases: list[Case], client: LLMClient) -> tuple[list[Evaluation], list[str]]:
    """Run ResuMetric on every case and convert the verdicts to sixdim-eval Evaluations."""
    evaluations, failed = [], []
    for case in cases:
        try:
            result = evaluate(case.source, case.output, client)
        except EvaluationError:
            failed.append(case.id)
            continue
        evaluations.append(
            Evaluation(
                case_id=case.id,
                scores={d: getattr(result.scores, d) for d in DIMENSIONS},
                summary=result.summary,
                judge=f"resumetric:{getattr(client, 'model', 'unknown')}",
                latency_ms=result.meta.latency_ms if result.meta else None,
            )
        )
    return evaluations, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--model", default=os.getenv("MODEL", "claude-sonnet-4-6"))
    parser.add_argument("--threshold", type=int, default=4, help="score counted as a pass (default 4)")
    args = parser.parse_args(argv)

    from evaluator import AnthropicClient

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("error: set ANTHROPIC_API_KEY", file=sys.stderr)
        return 2
    cases = read_cases(args.cases)
    labelled = [c for c in cases if c.human]
    print(f"{len(cases)} cases, {len(labelled)} with human labels", file=sys.stderr)

    evaluations, failed = judge_cases(cases, AnthropicClient(api_key=key, model=args.model))
    out = args.cases.parent / f"results-{args.model}.jsonl"
    write_results(out, evaluations)
    print(f"verdicts written to {out}; {len(failed)} unparseable: {failed}", file=sys.stderr)
    print(agreement_markdown(judge_agreement(cases, evaluations, args.threshold), args.threshold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The evaluation engine: prompt -> LLM -> defensively-parsed, validated scores.

The LLM client is injected (not created here) so it can be swapped for a fake
in tests. JSON parsing is defensive because models sometimes wrap output in
markdown fences or add stray prose despite instructions.
"""

from __future__ import annotations

import json
import re
import time
from statistics import fmean
from typing import Any, Protocol

from pydantic import ValidationError

from prompt import SYSTEM_PROMPT, build_user_message
from schemas import DIMENSIONS, ConsistencyResponse, DimensionSpread, EvaluateResponse, Meta


class LLMClient(Protocol):
    """Minimal interface the evaluator needs. The real client and test fakes both
    satisfy it, so evaluate() never depends on a concrete SDK.

    Clients may optionally expose `model` and `last_usage` ({input_tokens, output_tokens}).
    """

    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    """Thin wrapper around the Anthropic SDK that returns plain text and records token usage."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", timeout: float = 60.0):
        # Imported lazily so tests don't require the SDK or a key.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.last_usage: dict[str, int] | None = None

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        usage = getattr(message, "usage", None)
        if usage is not None:
            self.last_usage = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")


class EvaluationError(Exception):
    """Raised when the LLM output cannot be turned into a valid response."""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response that may include fences or prose."""
    text = raw.strip()
    fence = _FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def evaluate(source: str, document: str, client: LLMClient) -> EvaluateResponse:
    """Score a document against its source. Retries once if the model's reply is unusable."""
    user = build_user_message(source, document)
    started = time.perf_counter()
    last_error: Exception | None = None
    input_tokens = output_tokens = 0
    saw_usage = False

    for attempt in (1, 2):  # one initial attempt + one retry
        raw = client.complete(SYSTEM_PROMPT, user)
        usage = getattr(client, "last_usage", None)
        if usage:
            saw_usage = True
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
        try:
            data = _extract_json(raw)
            data.pop("overall", None)  # recomputed server-side from the scores
            data.pop("meta", None)
            response = EvaluateResponse(**data)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            last_error = exc
            continue
        response.meta = Meta(
            model=getattr(client, "model", None),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            attempts=attempt,
            input_tokens=input_tokens if saw_usage else None,
            output_tokens=output_tokens if saw_usage else None,
        )
        return response

    raise EvaluationError(f"Could not parse a valid evaluation from the model: {last_error}")


def evaluate_consistency(source: str, document: str, client: LLMClient, runs: int = 3) -> ConsistencyResponse:
    """Evaluate the same input several times and report how much each dimension moves.

    This operationalises the paper's Consistency dimension for the judge itself: if
    scores swing between identical runs, a single score should not be trusted.
    """
    evaluations = [evaluate(source, document, client) for _ in range(runs)]
    dims: dict[str, DimensionSpread] = {}
    for dim in DIMENSIONS:
        values = [getattr(e.scores, dim) for e in evaluations]
        dims[dim] = DimensionSpread(
            mean=round(fmean(values), 2), min=min(values), max=max(values), spread=max(values) - min(values)
        )
    return ConsistencyResponse(
        runs=runs,
        stable=all(d.spread <= 1 for d in dims.values()),
        dimensions=dims,
        overall_mean=round(fmean(e.overall for e in evaluations), 2),
        evaluations=evaluations,
    )

"""The evaluation engine: prompt -> LLM -> defensively-parsed scores.

The LLM client is injected (not created here) so it can be swapped for a mock
in tests. JSON parsing is defensive because models sometimes wrap output in
markdown fences or add stray prose despite instructions.
"""

import json
import re
from typing import Any, Protocol

from prompt import SYSTEM_PROMPT, build_user_message
from schemas import EvaluateResponse


class LLMClient(Protocol):
    """Minimal interface the evaluator needs. Real client and test mocks both
    satisfy this, so evaluate() never depends on a concrete SDK."""

    def complete(self, system: str, user: str) -> str:
        ...


class AnthropicClient:
    """Thin wrapper around the Anthropic SDK that returns plain text."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        # Imported lazily so tests don't require the SDK or a key.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate any text blocks the model returns.
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )


class EvaluationError(Exception):
    """Raised when the LLM output cannot be turned into a valid response."""


def _extract_json(raw: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response that may include fences or prose."""
    text = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first balanced-looking {...} span.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def evaluate(source: str, document: str, client: LLMClient) -> EvaluateResponse:
    """Score a document against its source. Retries once on parse failure."""
    user = build_user_message(source, document)

    last_error: Exception | None = None
    for _ in range(2):  # one initial attempt + one retry
        raw = client.complete(SYSTEM_PROMPT, user)
        try:
            data = _extract_json(raw)
            return EvaluateResponse(**data)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = exc
            continue

    raise EvaluationError(f"Could not parse a valid evaluation from the model: {last_error}")

# ResuMetric — Backend

FastAPI service that scores a generated document against its source material
across six dimensions (Completeness, Contextual Utilisation, Factual Accuracy,
Confidence Calibration, Consistency, Specification Adherence) and flags missing
or fabricated content.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then put your real ANTHROPIC_API_KEY in .env
uvicorn main:app --reload
```

Open the interactive docs at http://127.0.0.1:8000/docs and try `/evaluate`.

## Run the tests

```bash
cd backend
pytest
```

Tests mock the LLM, so they need **no API key and make no network calls**.

## Endpoints

| Method | Path        | Purpose                                  |
|--------|-------------|------------------------------------------|
| GET    | `/health`   | Liveness check → `{"status": "ok"}`      |
| POST   | `/evaluate` | Score a document. Body: `{source, document}` |

## How it's wired

- `prompt.py` — the six-dimension scoring prompt (the core IP).
- `schemas.py` — Pydantic request/response models; empty input is rejected with 422.
- `evaluator.py` — builds the prompt, calls the LLM through an injectable client,
  parses the JSON defensively (handles fences/prose), retries once on failure.
- `main.py` — routes, CORS, and clean error mapping (502 for unparseable model
  output, 503 for an LLM outage — never a raw stack trace).

The LLM client is an injected `Protocol`, which is why tests can swap in a stub.

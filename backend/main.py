"""FastAPI application entry point.

Run locally:  uvicorn main:app --reload
Interactive docs:  http://127.0.0.1:8000/docs
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from evaluator import AnthropicClient, EvaluationError, evaluate
from schemas import EvaluateRequest, EvaluateResponse

load_dotenv()

app = FastAPI(title="ResuMetric", version="0.1.0")

# Allow the local React dev server (and later your deployed frontend) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend URL before going public
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def get_client() -> AnthropicClient:
    """Build the LLM client once. Fails clearly if the key is missing."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env.")
    model = os.getenv("MODEL", "claude-sonnet-4-6")
    return AnthropicClient(api_key=api_key, model=model)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate_document(req: EvaluateRequest) -> EvaluateResponse:
    try:
        client = get_client()
    except RuntimeError as exc:
        # Misconfiguration on our side.
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        return evaluate(req.source, req.document, client)
    except EvaluationError as exc:
        # The model returned something we could not turn into a valid score.
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        # Network / API failure talking to the LLM. Never leak a stack trace.
        raise HTTPException(status_code=503, detail="Evaluation service is temporarily unavailable.")

"""FastAPI application entry point.

Run locally:  uvicorn main:app --reload
Web UI:       http://127.0.0.1:8000/
API docs:     http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from evaluator import AnthropicClient, EvaluationError, LLMClient, evaluate, evaluate_consistency
from schemas import (
    ConsistencyRequest,
    ConsistencyResponse,
    EvaluateRequest,
    EvaluateResponse,
    ExtractResponse,
)

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger("resumetric")

app = FastAPI(
    title="ResuMetric",
    version="0.2.0",
    description="Scores AI-generated documents against their source on six dimensions and flags "
    "missing or fabricated content. Based on https://doi.org/10.5281/zenodo.20102941",
)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------------- observability


@app.middleware("http")
async def request_log(request: Request, call_next):
    """Attach a request id and emit one structured JSON log line per request."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    log.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
    )
    return response


# --------------------------------------------------------------------------- dependencies


class RateLimiter:
    """In-memory sliding-window limit per client IP. Protects the API key on a public demo.

    Good enough for a single instance; a multi-instance deployment would use Redis.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        if self.per_minute <= 0:
            return
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        hits = self._hits[ip]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise HTTPException(status_code=429, detail="Too many requests - please wait a minute and try again.")
        hits.append(now)


rate_limit = RateLimiter(RATE_LIMIT_PER_MINUTE)


@lru_cache
def get_client() -> LLMClient:
    """Build the LLM client once. Fails clearly if the key is missing."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env.")
    return AnthropicClient(api_key=api_key, model=os.getenv("MODEL", "claude-sonnet-4-6"))


def _client_or_500() -> LLMClient:
    try:
        return get_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


def _run(fn, *args):
    """Map evaluator failures to clean HTTP errors. Never leak a stack trace."""
    try:
        return fn(*args)
    except EvaluationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        log.exception("LLM call failed")
        raise HTTPException(status_code=503, detail="Evaluation service is temporarily unavailable.") from None


# --------------------------------------------------------------------------- routes


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse, dependencies=[Depends(rate_limit)])
def evaluate_document(req: EvaluateRequest) -> EvaluateResponse:
    """Score one document against its source."""
    return _run(evaluate, req.source, req.document, _client_or_500())


@app.post("/evaluate/consistency", response_model=ConsistencyResponse, dependencies=[Depends(rate_limit)])
def evaluate_document_consistency(req: ConsistencyRequest) -> ConsistencyResponse:
    """Score the same input 2-5 times and report how much each dimension moves between runs."""
    return _run(evaluate_consistency, req.source, req.document, _client_or_500(), req.runs)


@app.post("/extract-text", response_model=ExtractResponse)
async def extract_text(file: Annotated[UploadFile, File()]) -> ExtractResponse:
    """Extract plain text from an uploaded PDF, TXT or Markdown file."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large.")
    name = file.filename or "upload"
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, ValueError):
            raise HTTPException(status_code=422, detail="Could not read this PDF.") from None
    elif suffix in {".txt", ".md"}:
        text = data.decode("utf-8", errors="replace")
    else:
        raise HTTPException(status_code=415, detail="Upload a .pdf, .txt or .md file.")
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text found. Scanned PDFs need OCR first.")
    return ExtractResponse(filename=name, characters=len(text), text=text)

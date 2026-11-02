"""Tests for the web UI, consistency, upload and rate-limit behaviour."""

import io
import json

import pytest
from fastapi.testclient import TestClient

import main

REPLY = json.dumps(
    {
        "scores": {
            "completeness": 5,
            "contextual_utilisation": 5,
            "factual_accuracy": 2,
            "confidence_calibration": 2,
            "consistency": 5,
            "specification_adherence": 5,
        },
        "flags": [{"section": "Contact", "issue": "Phone number not in source", "severity": "high"}],
        "summary": "Invented a phone number.",
    }
)


class Fake:
    model = "fake"

    def complete(self, system, user):
        return REPLY


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: Fake())
    return TestClient(main.app)


def test_index_serves_web_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ResuMetric" in resp.text and "<form" in resp.text


def test_request_id_header_is_set_and_echoed(client):
    assert client.get("/health").headers["x-request-id"]
    assert client.get("/health", headers={"x-request-id": "abc123"}).headers["x-request-id"] == "abc123"


def test_consistency_endpoint(client):
    resp = client.post("/evaluate/consistency", json={"source": "s", "document": "d", "runs": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == 2 and body["stable"] is True
    assert body["overall_mean"] == pytest.approx(4.0)


@pytest.mark.parametrize("runs", [1, 6])
def test_consistency_runs_are_bounded(client, runs):
    resp = client.post("/evaluate/consistency", json={"source": "s", "document": "d", "runs": runs})
    assert resp.status_code == 422


def test_oversized_input_rejected_before_llm_call(client, monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: pytest.fail("LLM should not be called"))
    resp = client.post("/evaluate", json={"source": "x" * 30001, "document": "d"})
    assert resp.status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main.rate_limit, "per_minute", 2)
    codes = [client.post("/evaluate", json={"source": "s", "document": "d"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_missing_api_key_is_a_clear_500(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    main.get_client.cache_clear()
    resp = TestClient(main.app).post("/evaluate", json={"source": "s", "document": "d"})
    assert resp.status_code == 500
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_extract_text_from_txt(client):
    resp = client.post("/extract-text", files={"file": ("cv.txt", b"Hello CV", "text/plain")})
    assert resp.status_code == 200
    assert resp.json() == {"filename": "cv.txt", "characters": 8, "text": "Hello CV"}


def test_extract_text_from_pdf(client):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=100)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 50 Td (MSc Computer Science) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)

    resp = client.post("/extract-text", files={"file": ("cv.pdf", buf.getvalue(), "application/pdf")})
    assert resp.status_code == 200
    assert "MSc Computer Science" in resp.json()["text"]


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [("cv.docx", b"x", 415), ("cv.pdf", b"not a pdf", 422), ("empty.txt", b"   ", 422)],
)
def test_extract_text_errors(client, name, data, code):
    assert client.post("/extract-text", files={"file": (name, data)}).status_code == code

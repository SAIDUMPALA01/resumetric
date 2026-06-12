"""API tests. The LLM client is overridden so tests are fast, free, and
deterministic - no network and no API key required."""

from fastapi.testclient import TestClient

import main
from evaluator import EvaluationError

client = TestClient(main.app)

VALID_JSON = """{
  "scores": {
    "completeness": 5, "contextual_utilisation": 5, "factual_accuracy": 5,
    "confidence_calibration": 4, "consistency": 5, "specification_adherence": 5
  },
  "overall": 4.83, "flags": [], "summary": "Clean, faithful document."
}"""


class FakeClient:
    def __init__(self, response):
        self._response = response

    def complete(self, system, user):
        return self._response


def teardown_function():
    # Clear any dependency override between tests.
    main.app.dependency_overrides.clear()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_evaluate_happy_path(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient(VALID_JSON))
    resp = client.post("/evaluate", json={"source": "transcript", "document": "cv text"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] == 4.83
    assert body["scores"]["completeness"] == 5


def test_evaluate_rejects_empty_input(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient(VALID_JSON))
    resp = client.post("/evaluate", json={"source": "", "document": "cv text"})
    assert resp.status_code == 422  # Pydantic validation


def test_evaluate_handles_unparseable_model_output(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient("not json"))
    resp = client.post("/evaluate", json={"source": "transcript", "document": "cv"})
    assert resp.status_code == 502


def test_evaluate_handles_llm_outage(monkeypatch):
    class BrokenClient:
        def complete(self, system, user):
            raise ConnectionError("API down")

    monkeypatch.setattr(main, "get_client", lambda: BrokenClient())
    resp = client.post("/evaluate", json={"source": "transcript", "document": "cv"})
    assert resp.status_code == 503

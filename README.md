# ResuMetric

**An automated document-quality checker that detects missing and fabricated content in AI-generated CVs and documents — built on a published six-dimension evaluation framework.**

> Operationalises the research in *"AI Model Performance in CV Generation and Consistency Testing: A Practical Six-Dimension Evaluation Framework"* (Zenodo, 2026) — [DOI: 10.5281/zenodo.20102941](https://doi.org/10.5281/zenodo.20102941).

<!-- Add a screenshot or GIF of the app here once you have one. It's the first thing visitors look at.
![ResuMetric demo](docs/demo.gif)
-->

🔗 **Live demo:** _add your deployed URL here_

---

## Why this exists

Large language models often produce documents that *look* finished but quietly leave sections empty, ignore information they were given, or invent details — all presented with total confidence and no warning to the user. My research identified this as the "invisible failure" and proposed a six-dimension framework for measuring it.

ResuMetric turns that framework into a working tool. You give it a generated document plus the source material it should have been built from, and it scores the document, flags anything missing or fabricated, and returns an honest verdict.

---

## Features

- **Six-dimension scoring** — Completeness, Contextual Utilisation, Factual Accuracy, Confidence Calibration, Consistency, and Specification Adherence, each scored 1–5.
- **Hallucination & gap flagging** — names the exact section and the problem, with a severity level.
- **Honest-by-design** — the evaluator itself uses the *MISSING instruction* technique from the research so it never invents a justification for content it can't ground in the source.
- **Clean REST API** — typed requests/responses, input validation, and graceful error handling (never leaks a stack trace).
- **Defensive LLM parsing** — copes with markdown fences and stray prose in model output, and retries once before failing.
- **Tested** — schema validation, JSON-parsing edge cases, and endpoint behaviour, all with the LLM mocked (no API key or network needed to run the suite).

---

## Tech stack

**Backend:** Python · FastAPI · Pydantic · Anthropic API
**Frontend:** React · Vite _(in progress)_
**Testing:** pytest
**Deployment:** Render / Railway / Fly.io

---

## Quick start

```bash
# 1. Set up the backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Confirm everything works (no API key needed — the LLM is mocked)
pytest                             # expect: 17 passed

# 3. Add your API key
cp .env.example .env               # then paste your ANTHROPIC_API_KEY into .env

# 4. Run the server
uvicorn main:app --reload
```

Open the interactive docs at **http://127.0.0.1:8000/docs** and try the `/evaluate` endpoint.

---

## Using the API

**`POST /evaluate`**

Request:

```json
{
  "source": "Sai Dumpala. MSc Computer Science, Birmingham City University. Built a CNN pneumonia detector, 96.2% accuracy.",
  "document": "Sai Dumpala — Software Engineer. MSc Computer Science. Phone: +91 9876543210. Built an e-commerce backend."
}
```

Response:

```json
{
  "scores": {
    "completeness": 4,
    "contextual_utilisation": 3,
    "factual_accuracy": 2,
    "confidence_calibration": 2,
    "consistency": 4,
    "specification_adherence": 5
  },
  "overall": 3.33,
  "flags": [
    { "section": "Contact", "issue": "Phone number not present in source", "severity": "high" },
    { "section": "Projects", "issue": "E-commerce backend not present in source", "severity": "high" }
  ],
  "summary": "Well-structured but contains a fabricated phone number and project absent from the source."
}
```

**`GET /health`** → `{ "status": "ok" }`

---

## How it works

```
React UI  ──HTTPS/JSON──►  FastAPI  ──prompt──►  LLM (Anthropic)
   (form + scorecard) ◄── scores + flags ◄── structured JSON
```

1. The frontend sends the source text and the document to `/evaluate`.
2. FastAPI validates the input (empty fields are rejected before any LLM call).
3. The evaluator injects them into the six-dimension scoring prompt and calls the model.
4. The model's JSON response is parsed defensively, validated against the schema, and returned.

---

## Project structure

```
resumetric/
├── backend/
│   ├── main.py          # FastAPI routes, CORS, error handling
│   ├── evaluator.py     # prompt → LLM → defensive JSON parsing (injectable client)
│   ├── schemas.py       # Pydantic request/response models
│   ├── prompt.py        # the six-dimension scoring prompt
│   ├── requirements.txt
│   ├── .env.example
│   └── tests/           # schema, parsing, and API tests (LLM mocked)
├── frontend/            # React + Vite UI (in progress)
└── README.md
```

---

## Running the tests

```bash
cd backend
pytest
```

The tests mock the LLM, so they're fast, free, and need no API key.

---

## Roadmap

- [ ] React frontend with an upload form and visual scorecard
- [ ] PDF upload and text extraction
- [ ] "Run twice" mode to surface the Consistency dimension live
- [ ] Side-by-side comparison of two documents
- [ ] Public deployment

---

## Author

**Sai Dumpala** — MSc Computer Science, Birmingham City University
[LinkedIn](https://www.linkedin.com/in/sai-dumpala) · [GitHub](https://github.com/SAIDUMPALA01) · [ORCID](https://orcid.org/0009-0001-0260-0072) · [Research paper](https://doi.org/10.5281/zenodo.20102941)

# ForgeMind AI — Industrial Intelligence Copilot

**Engineering Intelligence. Empowering Industry.**

ForgeMind AI is a Generative AI + Retrieval-Augmented Generation (RAG) app that helps manufacturing teams find answers in equipment manuals, SOPs, maintenance records and troubleshooting documents. Ask a question in natural language and get an AI answer backed by source excerpts.

## Features
- Industrial AI assistant for equipment, maintenance and procedures
- Document Q&A over uploaded PDFs
- Source citations (retrieved excerpts shown with each answer)
- Equipment registry and maintenance work orders (sample data)
- Semantic search (Sentence Transformers + FAISS) with keyword fallback
- Dashboard (Next.js) and Swagger API docs (FastAPI)
- Evaluation starter benchmark

## Architecture
```
PDF -> pdf_loader -> chunker -> embeddings -> FAISS index
Question -> search (FAISS or keyword) -> top-k chunks -> Gemini -> answer + sources
```

## Quick start

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env                           # add GEMINI_API_KEY
# run from the project root so ./data paths resolve
cd .. && uvicorn backend.app.main:app --reload --port 8000
```
Swagger UI: http://localhost:8000/docs

Optional semantic search: `pip install sentence-transformers faiss-cpu` and set `ENABLE_SEMANTIC_SEARCH=true`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Dashboard: http://localhost:3000

### Tests
```bash
pytest backend/app/tests
```

## Main endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | Health and config status |
| GET | /api/equipment | Equipment registry |
| GET | /api/maintenance | Work orders |
| POST | /api/documents/upload | Upload and index a PDF |
| GET | /api/documents | List indexed documents |
| POST | /api/ask | Ask a question `{question, top_k?}` |

## Without a Gemini key
The app still runs: `/api/ask` returns the top retrieved excerpts as the answer, so you can test retrieval before adding a key.

## Evaluation
`evaluation/benchmark.json` holds sample questions with expected keywords for future retrieval and answer-quality testing.

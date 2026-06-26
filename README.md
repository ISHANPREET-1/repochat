# RepoChat 🔍

> Ask anything about any GitHub repository. Get cited answers from the actual source code.

## Live Demo
[Coming soon]

## What it does
Paste any public GitHub repo URL → RepoChat indexes the entire codebase → ask questions in natural language → get answers with exact file and line number citations.

## Tech Stack
- **Backend:** FastAPI, Python
- **Embeddings:** Cohere API
- **Vector DB:** Qdrant Cloud
- **LLM:** OpenRouter (free models)
- **Frontend:** Next.js, Tailwind CSS

## How RAG works here
1. Clone repo → chunk code by function/class boundaries
2. Generate embeddings via Cohere
3. Store vectors in Qdrant Cloud
4. On question → embed query → find similar chunks → send to LLM with context
5. LLM returns cited answer with file paths and line numbers

## Run locally
```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Environment Variables
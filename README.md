# RepoChat 🔍

> Ask anything about any GitHub repository. Get cited answers from the actual source code.

## Live Demo
🚀 **[Try RepoChat Live Here](https://repochat-seven.vercel.app)**

*Note: The backend is hosted on a free Render tier and may take 45-60 seconds to spin up on the very first request.*

<img width="1438" height="812" alt="image" src="https://github.com/user-attachments/assets/25251a62-825e-40b6-95c5-a4bac4cff1fe" />


## What it does
Paste any public GitHub repo URL → RepoChat indexes the entire codebase → ask questions in natural language → get answers with exact file and line number citations.

## Tech Stack
- **Backend:** FastAPI, Python
- **Embeddings:** Cohere API
- **Vector DB:** Qdrant Cloud
- **LLM:** OpenRouter (free models)
- **Frontend:** Next.js, Tailwind CSS

## How RAG Works Under the Hood
1. Clone the target repo and chunk the code by function/class boundaries.
2. Generate semantic embeddings via Cohere.
3. Store the vector embeddings in Qdrant Cloud.
4. On user question → embed the query → retrieve similar chunks → send to LLM with context.
5. The LLM returns a cited answer grounded strictly in the source code, referencing exact file paths and line numbers.

## Run Locally

```bash
# 1. Clone the repository
git clone [https://github.com/yourusername/repochat.git](https://github.com/yourusername/repochat.git)
cd repochat

# 2. Start the Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Start the Frontend (in a new terminal)
cd ../frontend
npm install
npm run dev

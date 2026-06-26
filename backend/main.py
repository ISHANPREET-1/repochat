"""
main.py

FastAPI app exposing two endpoints:
  POST /ingest  — clone a GitHub repo and index it
  POST /chat    — ask a question about an indexed repo
"""

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Dict

from ingestion import ingest_repo
from retrieval import chat_with_repo

app = FastAPI(
    title="RepoChat API",
    description="RAG-powered Q&A over any GitHub repository",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class IngestRequest(BaseModel):
    repo_url: str  # e.g. "https://github.com/owner/repo"

class IngestResponse(BaseModel):
    repo_id: str
    repo_url: str
    files_processed: int
    chunks_stored: int
    status: str

class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    repo_id: str
    question: str
    chat_history: List[ChatMessage] = []

class Source(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    relevance_score: float

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """
    Clone a public GitHub repo, chunk all source files,
    embed them, and store in Qdrant. Returns a repo_id
    to use in subsequent /chat calls.
    """
    try:
        result = await ingest_repo(request.repo_url)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Answer a question about a previously ingested repo.
    Accepts optional chat_history for multi-turn conversations.
    """
    try:
        history = [msg.model_dump() for msg in request.chat_history]
        result = await chat_with_repo(
            repo_id=request.repo_id,
            question=request.question,
            chat_history=history,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
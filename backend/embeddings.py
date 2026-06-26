"""
embeddings.py
Uses Cohere API for embeddings (fast, free tier)
and Qdrant Cloud for vector storage (permanent, deployable)
"""

import os
import uuid
from typing import List, Dict
import cohere
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Cohere client
co = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))

# Qdrant Cloud client — falls back to local if cloud env vars not set
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if QDRANT_URL and QDRANT_API_KEY:
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    print("[qdrant] Connected to Qdrant Cloud")
else:
    qdrant = QdrantClient(path="./qdrant_storage")
    print("[qdrant] Using local Qdrant storage")

EMBEDDING_MODEL = "embed-english-v3.0"
EMBEDDING_DIM = 1024  # embed-english-v3.0 dimension


def _collection_name(repo_id: str) -> str:
    return f"repo_{repo_id}"


def _ensure_collection(repo_id: str) -> str:
    name = _collection_name(repo_id)
    existing = {c.name for c in qdrant.get_collections().collections}
    if name not in existing:
        qdrant.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"[qdrant] Created collection: {name}")
    return name


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed texts using Cohere API in batches of 96."""
    all_embeddings = []
    batch_size = 96

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = co.embed(
            texts=batch,
            model=EMBEDDING_MODEL,
            input_type="search_document",
        )
        all_embeddings.extend(response.embeddings)
        print(f"[cohere] Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

    return all_embeddings


async def embed_and_store(repo_id: str, chunks: List[Dict]) -> None:
    collection_name = _ensure_collection(repo_id)

    texts = [
        f"File: {chunk['file_path']}\n\n{chunk['content']}"
        for chunk in chunks
    ]

    embeddings = await embed_texts(texts)

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "content": chunk["content"],
                "file_path": chunk["file_path"],
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
                "repo_id": repo_id,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    batch_size = 100
    for i in range(0, len(points), batch_size):
        qdrant.upsert(
            collection_name=collection_name,
            points=points[i:i + batch_size],
        )

    print(f"[qdrant] Stored {len(points)} vectors in '{collection_name}'")


async def search(repo_id: str, query: str, top_k: int = 8) -> List[Dict]:
    collection_name = _collection_name(repo_id)

    response = co.embed(
        texts=[query],
        model=EMBEDDING_MODEL,
        input_type="search_query",
    )
    query_vector = response.embeddings[0]

    results = qdrant.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
    )

    return [
        {
            "content": hit.payload["content"],
            "file_path": hit.payload["file_path"],
            "start_line": hit.payload["start_line"],
            "end_line": hit.payload["end_line"],
            "score": hit.score,
        }
        for hit in results.points
    ]
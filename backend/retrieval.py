"""
retrieval.py

Retrieves relevant code chunks from Qdrant and uses a FREE model via
OpenRouter (openrouter.ai) to generate grounded, cited answers.

Free models available on OpenRouter:
  - meta-llama/llama-3.1-8b-instruct:free
  - google/gemma-2-9b-it:free
  - mistralai/mistral-7b-instruct:free
"""

import os
from typing import List, Dict
from openai import OpenAI  # OpenRouter uses the same interface as OpenAI
from embeddings import search

# OpenRouter is OpenAI-compatible — just change the base_url
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# Free model — change this to any free model on openrouter.ai/models
FREE_MODEL = "openai/gpt-oss-20b:free"

SYSTEM_PROMPT = """You are RepoChat, an expert code assistant. 
Your primary goal is to provide clear, human-readable explanations.

STRICT FORMATTING RULES:
1. Use a clear H2 or H3 heading for the main topic (e.g., "## Query-Execution Flow").
2. Use a short introductory sentence.
3. Use numbered lists (1., 2., 3.) for step-by-step processes or ordered information.
4. Use standard bullet points (-) for non-ordered details.
5. NEVER use pipe-delimited tables or '||' separators.
6. Use fenced code blocks (```python) for code.
7. Use inline code (e.g., `file_name.py`) for file paths or variables.

Guidelines:
- Base your answer ONLY on the provided code context.
- Always cite source files and line numbers.
- Be concise but complete—explain what the code does AND why it matters."""


def _format_context(chunks: List[Dict]) -> str:
    """Render retrieved chunks as numbered, labelled code blocks."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[Source {i}] {chunk['file_path']} "
            f"(lines {chunk['start_line']}–{chunk['end_line']})\n"
            f"```\n{chunk['content']}\n```"
        )
    return "\n\n".join(parts)


async def chat_with_repo(
    repo_id: str,
    question: str,
    chat_history: List[Dict],
) -> Dict:
    """
    1. Retrieve the top-k most relevant chunks for the question.
    2. Build a prompt that includes the chunks as grounding context.
    3. Call the LLM via OpenRouter and return the answer + sources.
    """
    chunks = await search(repo_id, question, top_k=8)

    if not chunks:
        return {
            "answer": (
                "I couldn't find relevant code for that question. "
                "Try rephrasing or asking about a specific file, function, or feature."
            ),
            "sources": [],
        }

    context = _format_context(chunks)

    # Build message history (keep last 6 turns)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in chat_history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Inject retrieved context into the latest user message
    messages.append({
        "role": "user",
        "content": (
            f"Here are the most relevant code snippets from the repository:\n\n"
            f"{context}\n\n"
            f"Question: {question}"
        ),
    })

    response = client.chat.completions.create(
        model=FREE_MODEL,
        messages=messages,
        max_tokens=2048,
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": [
            {
                "file_path": c["file_path"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "relevance_score": round(c["score"], 3),
            }
            for c in chunks[:5]
        ],
    }
"""
retrieval.py
Retrieves relevant code chunks from Qdrant and uses a fallback
system to query FREE models via OpenRouter.
"""

import os
from typing import List, Dict
from openai import OpenAI
from embeddings import search

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

AVAILABLE_MODELS = [
    "openrouter/free",
    "openai/gpt-oss-20b:free",
    "google/gemma-3-12b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-v3:free",
]

SYSTEM_PROMPT = """You are RepoChat, an expert code assistant that answers questions about a specific GitHub repository.

FORMATTING INSTRUCTIONS:
- Use markdown paragraphs, bold headings (##), bullet points (-) or numbered lists.
- NO tables or pipe characters anywhere.
- Use fenced code blocks with language tags (```python) for code.
- Use backticks for inline file paths or identifiers.

ANSWERING GUIDELINES:
- Base your answer ONLY on the provided code context.
- Always cite source files and line numbers.
- If context is insufficient, say so clearly."""


def _format_context(chunks: List[Dict]) -> str:
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

    # 1. Retrieve chunks
    try:
        chunks = await search(repo_id, question, top_k=8)
    except Exception as e:
        return {"answer": f"Error searching vector database: {str(e)}", "sources": []}

    if not chunks:
        return {
            "answer": "I couldn't find relevant code for that question. Try rephrasing or asking about a specific file or function.",
            "sources": [],
        }

    # 2. Build messages
    context = _format_context(chunks)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in chat_history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": f"Relevant snippets:\n\n{context}\n\nQuestion: {question}"
    })

    # 3. Fallback loop — try each model until one works
    last_error = ""
    for model in AVAILABLE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
            )
            if response and response.choices and response.choices[0].message:
                return {
                    "answer": response.choices[0].message.content,
                    "sources": [
                        {
                            "file_path": c["file_path"],
                            "start_line": c["start_line"],
                            "end_line": c["end_line"],
                            "relevance_score": round(c.get("score", 0.0), 3),
                        }
                        for c in chunks[:5]
                    ],
                }
        except Exception as exc:
            last_error = str(exc).lower()
            print(f"[retrieval] Model {model} failed: {exc}")
            continue

    # 4. All models failed
    if "429" in last_error or "rate" in last_error:
        answer = "## ⚠️ High Traffic\n\nAll AI models are currently rate limited. Please wait 15 seconds and try again."
    elif "401" in last_error or "unauthorized" in last_error:
        answer = "## 🔑 API Key Error\n\nPlease check the API key configuration."
    else:
        answer = f"## 🔌 Connection Error\n\nUnable to reach AI provider. Error: {last_error}"

    return {"answer": answer, "sources": []}
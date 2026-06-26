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

SYSTEM_PROMPT = """You are RepoChat, an expert code assistant that answers questions about a specific GitHub repository.

You will receive relevant code snippets retrieved from the codebase, then the user's question.

CRITICAL FORMATTING INSTRUCTIONS:
1. Direct Text and Lists Only: Present your response using standard markdown paragraphs, bold headings (##), and clear bullet points (-) or numbered lists (1.).
2. ABSOLUTELY NO TABLES: Do not use the pipe character '|' or markdown table structures anywhere in your response. Even if the retrieved source code snippets or documentation contain tables, you MUST parse that data and present it as standard sentences or bullet points.
3. Clean Layout: Ensure there are empty line breaks between sections to keep the text readable line-by-line. Do not cram ideas together.
4. Code Snippets: Use standard fenced code blocks with language tags (e.g., ```python) for code, and backticks (`like_this`) for file paths or inline identifiers.

CRITICAL ANSWERING GUIDELINES:
- Base your answer ONLY on the provided code context — do not invent behavior.
- Always cite source files and line numbers when referencing specific code.
- If the context doesn't contain enough information, say so clearly.
- Be concise but complete — explain what the code does AND why it matters."""

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
    try:
        chunks = await search(repo_id, question, top_k=8)
    except Exception as e:
        return {
            "answer": f"Error searching vector database: {str(e)}",
            "sources": []
        }

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

    try:
        response = client.chat.completions.create(
            model=FREE_MODEL,
            messages=messages,
            max_tokens=2048,
        )
        
        # Safeguard: Extract content safely without assuming it exists
        if response and response.choices and response.choices[0].message:
            answer_text = response.choices[0].message.content
        else:
            answer_text = None
            
    except Exception as exc:
        answer_text = f"An API communications error occurred: {str(exc)}"

    # Ensure answer_text is never None or empty to prevent Pydantic response validation crashes
    if not answer_text or answer_text.strip() == "":
        answer_text = (
            "The model returned an empty response or timed out due to heavy server load. "
            "Please try rephrasing your query slightly or try again."
        )

    return {
        "answer": answer_text,
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
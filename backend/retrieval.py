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
        error_msg = str(exc).lower()
        
        # Detect Rate Limits (429)
        if "429" in error_msg or "rate-limited" in error_msg:
            answer_text = (
                "## ⚠️ High Global Traffic (Rate Limit)\n\n"
                "**What happened:** The shared public AI model is currently handling a high volume of traffic and has temporarily paused new requests.\n\n"
                "**What you can do:**\n"
                "- **Wait a moment:** This is a temporary cooldown. Please try asking your question again in 10-15 seconds.\n"
                "- **Switch models:** If the issue persists, the project administrator can easily swap the backend to a less congested model like Llama 3.1 or Gemma 2."
            )
        # Detect Authentication Issues (401)
        elif "401" in error_msg or "api_key" in error_msg or "unauthorized" in error_msg:
            answer_text = (
                "## 🔑 API Key Error\n\n"
                "**What happened:** The application was unable to verify its connection credentials with the AI provider.\n\n"
                "**What you can do:**\n"
                "- **Check your environment:** Ensure that the `OPENROUTER_API_KEY` variable is correctly configured in your server environment."
            )
        # Fallback for general API disconnects
        else:
            answer_text = (
                "## 🔌 Connection Interrupted\n\n"
                "**What happened:** An unexpected network timeout or error occurred while communicating with the upstream AI provider.\n\n"
                "**What you can do:**\n"
                "- Try resubmitting your question.\n"
                "- If this continues, check the application server logs."
            )

    # Ensure answer_text is never None or empty to prevent Pydantic response validation crashes
    if not answer_text or answer_text.strip() == "":
        answer_text = (
            "## ⏳ Model Timeout\n\n"
            "**What happened:** The AI model took too long to respond or returned an empty payload due to heavy server load.\n\n"
            "**What you can do:**\n"
            "- Try asking a slightly different or more specific question to prompt a faster response."
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
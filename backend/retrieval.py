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
# Reverting back to the model that actually worked
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

    """
retrieval.py

Retrieves relevant code chunks from Qdrant and uses a fallback system
to query FREE models via OpenRouter (openrouter.ai).
"""

import os
from typing import List, Dict
from openai import OpenAI
from embeddings import search

# OpenRouter configuration
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# Prioritized list of stable, high-performance free models
AVAILABLE_MODELS = [
    "openai/gpt-oss-20b:free",
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free"
]

SYSTEM_PROMPT = """You are RepoChat, an expert code assistant that answers questions about a specific GitHub repository.

CRITICAL FORMATTING INSTRUCTIONS:
1. Direct Text and Lists Only: Present your response using standard markdown paragraphs, bold headings (##), and clear bullet points (-) or numbered lists (1.).
2. ABSOLUTELY NO TABLES: Do not use pipes or table structures.
3. Clean Layout: Use empty line breaks between sections.
4. Code Snippets: Use fenced code blocks (```python) for code, and backticks (`like_this`) for file paths/identifiers.

CRITICAL ANSWERING GUIDELINES:
- Base your answer ONLY on the provided code context.
- Always cite source files and line numbers.
- If the context doesn't contain enough information, say so clearly."""

def _format_context(chunks: List[Dict]) -> str:
    """Render retrieved chunks as numbered, labelled code blocks."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[Source {i}] {chunk['file_path']} (lines {chunk['start_line']}–{chunk['end_line']})\n"
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
        return {"answer": "I couldn't find relevant code for that question.", "sources": []}

    # 2. Build Prompt
    context = _format_context(chunks)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + \
               [{"role": msg["role"], "content": msg["content"]} for msg in chat_history[-6:]]
    
    messages.append({
        "role": "user",
        "content": f"Relevant snippets:\n\n{context}\n\nQuestion: {question}"
    })

    # 3. Fallback Loop: Try each model until one succeeds
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
                        {"file_path": c["file_path"], "start_line": c["start_line"], "end_line": c["end_line"], "relevance_score": round(c.get("score", 0.0), 3)}
                        for c in chunks[:5]
                    ]
                }
        except Exception as exc:
            last_error = str(exc).lower()
            continue # Move to the next model if this one fails

    # 4. Professional Error Handling (if all models fail)
    if "429" in last_error or "rate-limited" in last_error:
        answer_text = (
            "## ⚠️ High Global Traffic\n\n"
            "The AI models are currently overwhelmed. Please wait 15 seconds and try again."
        )
    elif "401" in last_error or "unauthorized" in last_error:
        answer_text = (
            "## 🔑 API Key Error\n\n"
            "Please check the application server environment configuration."
        )
    else:
        answer_text = (
            "## 🔌 Connection Interrupted\n\n"
            "Unable to reach AI provider. Diagnostic: " + last_error
        )

    return {"answer": answer_text, "sources": []}
"""
ingestion.py

Handles cloning a GitHub repo, walking its files,
chunking code intelligently, and sending chunks for embedding.
"""

import re
import hashlib
import tempfile
from pathlib import Path
from typing import List, Dict

import git
from embeddings import embed_and_store

# ── File types we care about ──────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".cpp", ".c", ".h",
    ".cs", ".rb", ".php", ".swift", ".kt",
    ".md", ".txt", ".yaml", ".yml", ".toml",
}

# ── Directories to skip entirely ──────────────────────────────────────────────
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".next",
    "dist", "build", "venv", ".venv", "env",
    "vendor", "coverage", ".pytest_cache", ".mypy_cache",
}

MAX_FILE_SIZE = 100_000  # 100 KB — skip huge generated files


# ── Chunking helpers ──────────────────────────────────────────────────────────

def _chunk_python(content: str, file_path: str) -> List[Dict]:
    """Split Python files at top-level def / class / async def boundaries."""
    lines = content.split("\n")
    chunks, current, start = [], [], 0

    for i, line in enumerate(lines):
        is_boundary = (
            line.startswith("def ")
            or line.startswith("class ")
            or line.startswith("async def ")
        )
        if is_boundary and current and len("\n".join(current)) > 80:
            chunks.append({
                "content": "\n".join(current),
                "file_path": file_path,
                "start_line": start + 1,
                "end_line": i,
            })
            current, start = [line], i
        else:
            current.append(line)

    if current:
        chunks.append({
            "content": "\n".join(current),
            "file_path": file_path,
            "start_line": start + 1,
            "end_line": len(lines),
        })

    return [c for c in chunks if len(c["content"].strip()) > 50]


def _chunk_js(content: str, file_path: str) -> List[Dict]:
    """Split JS/TS files at function / class / export const boundaries."""
    patterns = [
        r"^(export\s+)?(default\s+)?(async\s+)?function\s+\w+",
        r"^(export\s+)?class\s+\w+",
        r"^(export\s+)?const\s+\w+\s*=\s*(async\s+)?\(",
        r"^(export\s+)?const\s+\w+\s*=\s*(async\s+)?\w+\s*=>",
    ]

    lines = content.split("\n")
    chunks, current, start = [], [], 0

    for i, line in enumerate(lines):
        is_boundary = any(re.match(p, line.strip()) for p in patterns)
        if is_boundary and current and len("\n".join(current)) > 80:
            chunks.append({
                "content": "\n".join(current),
                "file_path": file_path,
                "start_line": start + 1,
                "end_line": i,
            })
            current, start = [line], i
        else:
            current.append(line)

    if current:
        chunks.append({
            "content": "\n".join(current),
            "file_path": file_path,
            "start_line": start + 1,
            "end_line": len(lines),
        })

    return [c for c in chunks if len(c["content"].strip()) > 50]


def _chunk_markdown(content: str, file_path: str) -> List[Dict]:
    """Split markdown at h1/h2/h3 headings."""
    sections = re.split(r"\n(?=#{1,3} )", content)
    chunks = []
    line_counter = 1

    for section in sections:
        if section.strip():
            line_count = section.count("\n") + 1
            chunks.append({
                "content": section.strip(),
                "file_path": file_path,
                "start_line": line_counter,
                "end_line": line_counter + line_count,
            })
            line_counter += line_count

    return chunks


def _chunk_by_size(content: str, file_path: str, chunk_size=1500, overlap=200) -> List[Dict]:
    """Fallback: character-based chunking with overlap, ending at newlines."""
    chunks = []
    start = 0

    while start < len(content):
        end = start + chunk_size
        chunk_text = content[start:end]

        # Prefer splitting at a newline boundary
        last_newline = chunk_text.rfind("\n")
        if last_newline > chunk_size // 2:
            chunk_text = chunk_text[:last_newline]

        if chunk_text.strip():
            chars_before = content[:start]
            start_line = chars_before.count("\n") + 1
            end_line = start_line + chunk_text.count("\n")
            chunks.append({
                "content": chunk_text.strip(),
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
            })

        start += chunk_size - overlap

    return chunks


def chunk_code(content: str, file_path: str) -> List[Dict]:
    """
    Dispatch to the right chunker based on file extension.
    Falls back to size-based chunking if nothing better applies.
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".py":
        chunks = _chunk_python(content, file_path)
    elif ext in {".js", ".ts", ".jsx", ".tsx"}:
        chunks = _chunk_js(content, file_path)
    elif ext in {".md", ".txt"}:
        chunks = _chunk_markdown(content, file_path)
    else:
        chunks = []

    # If language-specific chunker produced nothing, fall back
    return chunks or _chunk_by_size(content, file_path)


# ── Main ingestion entry point ─────────────────────────────────────────────────

async def ingest_repo(repo_url: str) -> Dict:
    """
    Clone a GitHub repo, walk its files, chunk them, embed and store.
    Returns metadata about the ingestion.
    """
    # Stable ID derived from the URL
    repo_id = hashlib.md5(repo_url.encode()).hexdigest()[:12]

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"[ingest] Cloning {repo_url} …")

        # Shallow clone — much faster, we only need the latest snapshot
        git.Repo.clone_from(repo_url, tmpdir, depth=1)

        all_chunks: List[Dict] = []
        files_processed = 0

        for file_path in Path(tmpdir).rglob("*"):
            if not file_path.is_file():
                continue
            if any(skip in file_path.parts for skip in SKIP_DIRS):
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue

                relative_path = str(file_path.relative_to(tmpdir))
                chunks = chunk_code(content, relative_path)
                all_chunks.extend(chunks)
                files_processed += 1

            except Exception as exc:
                print(f"[ingest] Skipping {file_path}: {exc}")

        print(f"[ingest] {files_processed} files → {len(all_chunks)} chunks")

        await embed_and_store(repo_id, all_chunks)

    return {
        "repo_id": repo_id,
        "repo_url": repo_url,
        "files_processed": files_processed,
        "chunks_stored": len(all_chunks),
        "status": "ready",
    }
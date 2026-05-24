"""RAG pipeline backed by Ollama.

Flow on upload:
  text → chunk_text() → [embed each chunk via Ollama nomic-embed-text]
  → store in document_chunks table (user_id, material_id, embedding JSON)

Flow on chat:
  query → embed via Ollama → cosine similarity over user's chunks (numpy)
  → top-K context → Ollama llama3.2:1b → answer (streaming or one-shot)

Ollama is optional: falls back gracefully if the service is not reachable
(useful during local dev without Docker).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator, Optional, cast

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import DocumentChunk

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GEN_MODEL    = os.getenv("OLLAMA_GEN_MODEL",   "mistral:latest")
EMBED_TIMEOUT_SEC = float(os.getenv("RAG_EMBED_TIMEOUT_SEC", "8"))
GEN_TIMEOUT_SEC = float(os.getenv("RAG_GEN_TIMEOUT_SEC", "12"))

# Cache Ollama reachability so repeated requests do not stall on a dead model
# server. The app can still serve keyword and context-only fallbacks.
_ollama_reachable: Optional[bool] = None


async def _is_ollama_reachable() -> bool:
    global _ollama_reachable
    if _ollama_reachable is not None:
        return _ollama_reachable
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags", timeout=1.5)
            _ollama_reachable = response.status_code < 500
    except Exception:
        _ollama_reachable = False
    return _ollama_reachable

# Chunk parameters (word-based with overlap)
CHUNK_SIZE   = 300   # words per chunk
CHUNK_OVERLAP = 60   # words shared between consecutive chunks


def _clean_context_text(text: str) -> str:
    cleaned = re.sub(r"[\u2500-\u257f]{3,}", " ", text or "")
    cleaned = re.sub(r"\s*\|\s*", " ", cleaned)
    cleaned = re.sub(r"\[\d+\]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _format_sources(chunks: list[dict]) -> list[str]:
    seen: list[str] = []
    for chunk in chunks:
        filename = chunk.get("filename") or chunk.get("subject") or "Study material"
        if filename not in seen:
            seen.append(filename)
    return seen[:5]


def _build_tutor_answer(question: str, chunks: list[dict], llm_answer: str | None = None) -> dict:
    sources = _format_sources(chunks)
    key_points = []
    for chunk in chunks[:3]:
        snippet = _clean_context_text(chunk.get("text", ""))[:180]
        if snippet:
            key_points.append(snippet)

    answer_text = llm_answer.strip() if llm_answer else ""
    if not answer_text:
        summary = "I found the most relevant parts of your material and turned them into a short study guide."
        if key_points:
            answer_text = (
                f"## Simple Summary\n{summary}\n\n"
                f"## Direct Answer\n{_clean_context_text(chunks[0].get('text', ''))[:320]}\n\n"
                f"## Key Points\n- " + "\n- ".join(key_points)
            )
        else:
            answer_text = (
                "## Simple Summary\nI could not find enough indexed material yet.\n\n"
                "## Direct Answer\nUpload a PDF, PPT, or DOC file from the syllabus page so I can explain it like a tutor.\n\n"
                "## Suggested Questions\n- What are the main ideas in this topic?\n- Can you explain this in simpler terms?\n- Give me a quick practice question."
            )

    if "## Suggested Questions" not in answer_text:
        answer_text = (
            f"{answer_text.rstrip()}\n\n"
            "## Suggested Questions\n"
            f"- What is the easiest way to remember the core idea behind {question.strip()}?\n"
            f"- Can you explain the topic step by step with an example?\n"
            "- What is one likely exam question from this material?"
        )

    return {
        "answer": answer_text,
        "summary": _clean_context_text(chunks[0].get("text", ""))[:220] if chunks else "",
        "key_points": key_points,
        "suggested_questions": [
            f"What is the simplest way to understand {question.strip()}?",
            "Can you teach this topic with a short example?",
            "What should I revise first before an exam?",
        ],
        "sources": sources,
    }

# ── Text chunking ────────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        piece = " ".join(words[start:end])
        if len(piece.strip()) > 30:        # discard tiny fragments
            chunks.append(piece)
        if end >= len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Ollama helpers ───────────────────────────────────────────────────────────

async def _embed_one(text: str, client: httpx.AsyncClient) -> Optional[list[float]]:
    """Call Ollama /api/embeddings for a single text string."""
    try:
        r = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=EMBED_TIMEOUT_SEC,
        )
        if r.status_code == 200:
            return r.json().get("embedding")
    except Exception as exc:
        logger.debug("Ollama embed failed: %s", exc)
    return None


async def _embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed a list of texts in parallel (max 6 concurrent to avoid OOM)."""
    if not await _is_ollama_reachable():
        return [None] * len(texts)
    sem = asyncio.Semaphore(6)

    async def _bounded(text: str, client: httpx.AsyncClient) -> Optional[list[float]]:
        async with sem:
            return await _embed_one(text, client)

    async with httpx.AsyncClient() as client:
        return await asyncio.gather(*[_bounded(t, client) for t in texts])


# ── Indexing ─────────────────────────────────────────────────────────────────

async def index_document(
    *,
    user_id: int,
    material_id: int,
    text: str,
    subject: str,
    filename: str,
    db: AsyncSession,
) -> int:
    """Chunk, embed, and store a document's content.  Returns number of chunks stored."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = await _embed_batch(chunks)

    rows = [
        DocumentChunk(
            user_id=user_id,
            material_id=material_id,
            subject=subject,
            filename=filename,
            chunk_index=i,
            content=chunk,
            embedding=emb,          # None if Ollama was unavailable
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    db.add_all(rows)
    await db.commit()
    logger.info("Indexed %d chunks for user=%s material=%s", len(rows), user_id, material_id)
    return len(rows)


async def delete_chunks(material_id: int, db: AsyncSession) -> None:
    """Remove all stored chunks for a given material (called on file delete)."""
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.material_id == material_id)
    )
    for chunk in result.scalars().all():
        await db.delete(chunk)
    await db.commit()


# ── Retrieval ────────────────────────────────────────────────────────────────

async def retrieve(
    *,
    user_id: int,
    query: str,
    db: AsyncSession,
    material_id: int | None = None,
    k: int = 6,
) -> list[dict]:
    """Embed query, return top-k chunks by cosine similarity."""
    if not await _is_ollama_reachable():
        return await _keyword_fallback(user_id=user_id, query=query, db=db, material_id=material_id, k=k)

    # Embed the query
    async with httpx.AsyncClient() as client:
        q_emb = await _embed_one(query, client)

    if q_emb is None:
        # Ollama not available — fall back to simple keyword match
        return await _keyword_fallback(user_id=user_id, query=query, db=db, material_id=material_id, k=k)

    # Load user's embedded chunks
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.embedding.isnot(None))
    )
    chunks = result.scalars().all()
    if material_id is not None:
        chunks = [chunk for chunk in chunks if cast(Any, chunk).material_id == material_id]
    if not chunks:
        return []

    q_vec = np.array(q_emb, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec) + 1e-9

    scored = []
    for c in chunks:
        c_vec = np.array(c.embedding, dtype=np.float32)
        score = float(np.dot(q_vec, c_vec) / (q_norm * (np.linalg.norm(c_vec) + 1e-9)))
        scored.append({
            "text":     c.content,
            "filename": c.filename or "",
            "subject":  c.subject or "",
            "score":    score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


async def _keyword_fallback(
    *, user_id: int, query: str, db: AsyncSession, material_id: int | None, k: int
) -> list[dict]:
    """Simple keyword match when Ollama embedding is unavailable."""
    keywords = [w.lower() for w in query.split() if len(w) > 2]
    query_builder = select(DocumentChunk).where(DocumentChunk.user_id == user_id)
    if material_id is not None:
        query_builder = query_builder.where(DocumentChunk.material_id == material_id)
    result = await db.execute(query_builder)
    scored = []
    for c in result.scalars().all():
        hits = sum(1 for kw in keywords if kw in c.content.lower())
        if hits:
            scored.append({"text": c.content, "filename": c.filename or "",
                           "subject": c.subject or "", "score": hits})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


# ── Generation ───────────────────────────────────────────────────────────────

async def answer(
    *,
    user_id: int,
    question: str,
    db: AsyncSession,
    material_id: int | None = None,
) -> dict:
    """Full RAG: retrieve relevant chunks, then generate an answer with Ollama."""
    chunks = await retrieve(user_id=user_id, query=question, db=db, material_id=material_id)

    if not chunks:
        return _build_tutor_answer(question, [])

    context = "\n\n".join(
        f"[{i+1}] {c['filename'] or c['subject']}: {_clean_context_text(c['text'])}"
        for i, c in enumerate(chunks)
    )

    prompt = (
        "You are a patient tutor teaching a student from their uploaded material. "
        "Use only the context provided. Do not copy raw chunk separators, markdown delimiters, or OCR noise. "
        "Return a clear teaching answer in markdown with these sections exactly: "
        "## Simple Summary, ## Direct Answer, ## Key Points, ## Suggested Questions. "
        "Keep it concise but explanatory, like a real teacher.",
        "\n\nContext:\n",
        context,
        "\n\nStudent question:\n",
        question,
        "\n\nAnswer now:"
    )

    try:
        async with httpx.AsyncClient(timeout=GEN_TIMEOUT_SEC) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model":  GEN_MODEL,
                    "prompt": "".join(prompt),
                    "stream": False,
                    "options": {"temperature": 0.25, "num_predict": 450},
                },
            )
            if r.status_code == 200:
                llm_answer = r.json().get("response", "").strip()
                if llm_answer:
                    return _build_tutor_answer(question, chunks, llm_answer=llm_answer)
    except Exception as exc:
        logger.info("Ollama generate unavailable (%s) — using context-only fallback", exc)

    return _build_tutor_answer(question, chunks)


# ── Ollama health ─────────────────────────────────────────────────────────────

async def ollama_status() -> dict:
    """Return which Ollama models are available."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return {"reachable": True, "models": models}
    except Exception:
        pass
    return {"reachable": False, "models": []}


# ── Streaming generation ──────────────────────────────────────────────────────

async def answer_stream(
    *,
    user_id: int,
    question: str,
    db: AsyncSession,
    material_id: int | None = None,
) -> AsyncIterator[str]:
    """Streaming variant of answer(): yields raw token strings from Ollama.

    Falls back to yielding the full fallback text as one chunk if Ollama is
    unavailable, so the caller doesn't need special-case handling.
    """
    response = await answer(user_id=user_id, question=question, db=db, material_id=material_id)
    yield response.get("answer", "")

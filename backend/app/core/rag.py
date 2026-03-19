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
from typing import AsyncIterator, Optional

import httpx
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import DocumentChunk

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL  = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GEN_MODEL    = os.getenv("OLLAMA_GEN_MODEL",   "llama3.2:1b")

# Chunk parameters (word-based with overlap)
CHUNK_SIZE   = 300   # words per chunk
CHUNK_OVERLAP = 60   # words shared between consecutive chunks

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
            timeout=30.0,
        )
        if r.status_code == 200:
            return r.json().get("embedding")
    except Exception as exc:
        logger.debug("Ollama embed failed: %s", exc)
    return None


async def _embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed a list of texts in parallel (max 6 concurrent to avoid OOM)."""
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
    k: int = 6,
) -> list[dict]:
    """Embed query, return top-k chunks by cosine similarity."""
    # Embed the query
    async with httpx.AsyncClient() as client:
        q_emb = await _embed_one(query, client)

    if q_emb is None:
        # Ollama not available — fall back to simple keyword match
        return await _keyword_fallback(user_id=user_id, query=query, db=db, k=k)

    # Load user's embedded chunks
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.embedding.isnot(None))
    )
    chunks = result.scalars().all()
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
    *, user_id: int, query: str, db: AsyncSession, k: int
) -> list[dict]:
    """Simple keyword match when Ollama embedding is unavailable."""
    keywords = [w.lower() for w in query.split() if len(w) > 2]
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.user_id == user_id)
    )
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
) -> dict:
    """Full RAG: retrieve relevant chunks, then generate an answer with Ollama."""
    chunks = await retrieve(user_id=user_id, query=question, db=db)

    sources = list({c["filename"] for c in chunks if c["filename"]})

    if not chunks:
        return {
            "answer": (
                "I don't have any indexed study materials for your account yet. "
                "Upload a PDF or PPTX from the Syllabus & Files page and I'll be "
                "able to answer questions directly from your course content!"
            ),
            "sources": [],
        }

    context = "\n\n".join(
        f"[{i+1}] ({c['subject']}) {c['text']}"
        for i, c in enumerate(chunks)
    )

    prompt = (
        "You are a concise AI study assistant. Answer the student's question "
        "using ONLY the study material context below. "
        "Be educational, accurate, and brief (3-5 sentences max).\n\n"
        f"Study material context:\n{context}\n\n"
        f"Student question: {question}\n\n"
        "Answer:"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model":  GEN_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 350},
                },
            )
            if r.status_code == 200:
                llm_answer = r.json().get("response", "").strip()
                if llm_answer:
                    return {"answer": llm_answer, "sources": sources}
    except Exception as exc:
        logger.info("Ollama generate unavailable (%s) — using context-only fallback", exc)

    # ── Fallback: return well-formatted context snippets ──────────────────
    bullets = "\n\n".join(
        f"**From {c['filename']} ({c['subject']}):**\n{c['text'][:300]}{'...' if len(c['text']) > 300 else ''}"
        for c in chunks[:3]
    )
    fallback = (
        f"Here's the most relevant content I found in your study materials:\n\n"
        f"{bullets}\n\n"
        "_Note: The AI generation model (Ollama) isn't running. "
        "Start Ollama and pull `llama3.2:1b` for full LLM-powered answers._"
    )
    return {"answer": fallback, "sources": sources}


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
) -> AsyncIterator[str]:
    """Streaming variant of answer(): yields raw token strings from Ollama.

    Falls back to yielding the full fallback text as one chunk if Ollama is
    unavailable, so the caller doesn't need special-case handling.
    """
    chunks = await retrieve(user_id=user_id, query=question, db=db)

    if not chunks:
        yield (
            "I don't have any indexed study materials for your account yet. "
            "Upload a PDF or PPTX from the Syllabus & Files page and I'll be "
            "able to answer questions directly from your course content!"
        )
        return

    context = "\n\n".join(
        f"[{i+1}] ({c['subject']}) {c['text']}"
        for i, c in enumerate(chunks)
    )
    prompt = (
        "You are a concise AI study assistant. Answer the student's question "
        "using ONLY the study material context below. "
        "Be educational, accurate, and brief (3-5 sentences max).\n\n"
        f"Study material context:\n{context}\n\n"
        f"Student question: {question}\n\n"
        "Answer:"
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": GEN_MODEL,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"temperature": 0.3, "num_predict": 350},
                },
            ) as r:
                if r.status_code == 200:
                    async for line in r.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:
                            continue
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done"):
                            return
    except Exception as exc:
        logger.info("Ollama streaming unavailable (%s) — using context-only fallback", exc)

    # ── Fallback: emit formatted context snippets as a single chunk ──────────
    sources = list({c["filename"] for c in chunks if c["filename"]})
    fallback_lines = [
        f"From **{c['filename']}** ({c['subject']}):\n{c['text'][:300]}{'...' if len(c['text']) > 300 else ''}"
        for c in chunks[:3]
    ]
    yield (
        "Here's the most relevant content I found in your study materials:\n\n"
        + "\n\n".join(fallback_lines)
        + "\n\n_Note: The AI model (Ollama) isn't running. "
        "Start Ollama and pull `llama3.2:1b` for full LLM-powered answers._"
    )

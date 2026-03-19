"""Intelligent Syllabus Analysis & Adaptive Scheduling.

Technology stack and why:
  1. Ollama LLM (llama3.2:1b, already deployed):
     - Understands *domain knowledge* — knows that "Attention Mechanism" must
       come before "Transformers", that NLP and NNDL share foundational concepts.
     - Estimates topic difficulty from names + position in curriculum.
     - Detects prerequisites between topics within a subject (intra-subject graph).
     - Detects cross-subject relationships (NLP ↔ NNDL shared Attention concepts).
     - Fully offline, already running in Docker. No API keys, no cost.

  2. Pure-Python Topological Sort (Kahn's algorithm, stdlib only):
     - Models topic dependency DAG: directed edges A→B mean "learn A before B".
     - Topological sort gives a valid learning order that respects all prerequisites.
     - Betweenness-like heuristic: foundational topics (many dependents) come early.
     - No external graph library needed (avoids new Docker layer).

  3. Constraint-based Adaptive Scheduler (pure Python):
     - Difficulty multiplier: easier topics → shorter slots; harder → more days.
     - Subject interleaving: never blocks one subject; all subjects progress in parallel.
     - User priority: important subjects get proportionally more daily time.
     - User feedback: "need more time" stores per-topic override; "too hard"
       inserts a prerequisite review block before the topic.
     - Cross-subject scheduling: detected related topics are placed in nearby days.

Why NOT alternatives considered:
  - Spaced repetition (SM-2 / FSRS): Great for review, not for "what to learn first".
  - RL agents: Cold-start problem, needs training data, overkill for scheduling.
  - External knowledge graphs (Wikidata / Wikipedia): Internet-dependent, incomplete.
  - Semantic embeddings only (FAISS): Similarity ≠ prerequisite — related but
    not the same as "learn A before B".
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Docker Compose sets OLLAMA_URL=http://ollama:11434 explicitly.
# For local dev without Docker the default falls back to localhost.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GEN_MODEL  = os.getenv("OLLAMA_GEN_MODEL", "llama3.2:1b")

# Performance tuning knobs for large syllabus files.
LLM_SUBJECT_EXCERPT_CHARS = int(os.getenv("SYLLABUS_LLM_SUBJECT_EXCERPT_CHARS", "4500"))
LLM_SUBJECT_TIMEOUT_SEC = float(os.getenv("SYLLABUS_LLM_SUBJECT_TIMEOUT_SEC", "8"))
LLM_IDENTIFY_TIMEOUT_SEC = float(os.getenv("SYLLABUS_LLM_IDENTIFY_TIMEOUT_SEC", "8"))

# ---------------------------------------------------------------------------
# One-shot Ollama reachability check — cached after first call so every
# extraction attempt doesn't pay the full DNS / connection timeout cost.
# ---------------------------------------------------------------------------
_ollama_reachable: Optional[bool] = None


async def _is_ollama_reachable() -> bool:
    """Return True if Ollama is up; result is cached for the process lifetime."""
    global _ollama_reachable
    if _ollama_reachable is not None:
        return _ollama_reachable
    try:
        async with httpx.AsyncClient() as cli:
            r = await cli.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
            _ollama_reachable = r.status_code < 500
    except Exception:
        _ollama_reachable = False
    logger.info("Ollama reachable at %s: %s", OLLAMA_URL, _ollama_reachable)
    return _ollama_reachable


MAX_LLM_SUBJECTS_PER_DOC = int(os.getenv("SYLLABUS_MAX_LLM_SUBJECTS_PER_DOC", "3"))
SUBJECT_ANALYSIS_CONCURRENCY = int(os.getenv("SYLLABUS_SUBJECT_ANALYSIS_CONCURRENCY", "3"))
LARGE_DOC_CHAR_THRESHOLD = int(os.getenv("SYLLABUS_LARGE_DOC_CHAR_THRESHOLD", "120000"))

# ─────────────────────────────────────────────────────────────────────────────
# Difficulty constants
# ─────────────────────────────────────────────────────────────────────────────

DIFFICULTY_LABEL = {1: "Easy", 2: "Basic", 3: "Intermediate", 4: "Hard", 5: "Advanced"}

# Base hours per difficulty level
DIFFICULTY_HOURS = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.5, 5: 5.0}

# Difficulty multiplier applied to days-per-topic
DIFFICULTY_MULT = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.5, 5: 2.5}

TIME_SLOTS = ["09:00 AM", "11:00 AM", "02:00 PM", "05:00 PM", "08:00 PM"]


def build_time_slots(start_hour: int = 9, end_hour: int = 23, num_slots: int = 5) -> list[str]:
    """Build time slots within user's study window.
    
    Args:
        start_hour: Study start time (0-23, e.g., 9 for 9 AM)
        end_hour: Study end time (0-23, e.g., 23 for 11 PM)
        num_slots: Target number of slots to create (up to 5)
        
    Returns:
        List of time slot strings in HH:MM AM/PM format
    """
    start_hour = max(0, min(23, start_hour))
    end_hour = max(start_hour + 1, min(24, end_hour))
    
    # Calculate available hours for slot spacing
    available_hours = end_hour - start_hour
    
    # Adjust num_slots based on available window
    if available_hours <= 2:
        num_slots = 1
    elif available_hours <= 4:
        num_slots = 2
    elif available_hours <= 6:
        num_slots = max(2, min(num_slots, 3))
    else:
        num_slots = max(2, min(num_slots, 5))
    
    # Generate evenly-spaced slots
    slots = []
    for i in range(num_slots):
        # Distribute slots evenly across window
        slot_hour = start_hour + (available_hours / (num_slots + 1)) * (i + 1)
        slot_hour = int(slot_hour)
        
        # Convert to 12-hour format with AM/PM
        if slot_hour >= 12:
            ampm = "PM"
            display_hour = slot_hour if slot_hour == 12 else slot_hour - 12
        else:
            ampm = "AM"
            display_hour = slot_hour if slot_hour != 0 else 12
        
        slots.append(f"{display_hour:02d}:00 {ampm}")
    
    return slots if slots else TIME_SLOTS[:1]  # Fallback to first default slot


# ─────────────────────────────────────────────────────────────────────────────
# Domain heuristics for fallback difficulty estimation
# ─────────────────────────────────────────────────────────────────────────────

_DIFF_5_KW = {
    "proof", "derivation", "theorem", "optimization", "backpropagation",
    "transformer", "attention mechanism", "bert", "gpt", "eigenvector",
    "byzantine", "paxos", "raft", "consensus", "distributed consensus",
    "variational", "monte carlo", "expectation maximization", "hmm",
    "conditional random field", "crf", "lstm", "gru", "gan",
}
_DIFF_4_KW = {
    "neural network", "deep learning", "convolutional", "recurrent",
    "gradient descent", "regularization", "convolution", "dependency parsing",
    "word embeddings", "word2vec", "glove", "transformer architecture",
    "language model", "cloud architecture", "kubernetes", "distributed",
    "machine learning algorithm", "reinforcement learning",
}
_DIFF_2_KW = {
    "introduction", "overview", "basics", "fundamentals", "what is",
    "history", "motivation", "simple", "linear regression", "classification",
    "supervised", "unsupervised", "tokenization", "stemming", "lemmatization",
}
_DIFF_1_KW = {
    "definition", "prerequisites", "course overview", "syllabus review",
    "setup", "installation", "getting started",
}


def _extract_subject_code(text: str, subject: str) -> str:
    """Try to extract a subject/course code from the document text or subject name.

    Handles common university patterns:
      - (CS501) or [BCA204] — code in parentheses/brackets before course title
      - 21CS502 — year-prefixed codes (Indian universities)
      - CS-301, ECE 4521 — letters + optional separator + 3-4 digits
      - embedded in subject name: "Data Structures (DS301)"
    """
    # 1. Check if a code pattern is already embedded in the subject name
    m = re.search(r'\b([A-Z]{1,6}[-\s]?\d{3,4})\b', subject)
    if m:
        return m.group(1).replace(' ', '')

    # 2. Scan the first 1500 chars of the document for a code near the subject name
    excerpt = text[:1500]

    # Indian university pattern: (CODE) COURSE TITLE  or  CODE: COURSE TITLE
    patterns = [
        r'\(([A-Z0-9]{4,10})\)',                    # (CS501) or (21CS502)
        r'\[([A-Z0-9]{4,10})\]',                    # [BCA204]
        r'\b(\d{2}[A-Z]{2,4}\d{3,4})\b',           # 21CS502
        r'\b([A-Z]{2,6}[-–]?\d{3,4})\b',           # CS-301 or ECE4521
        r'(?:Code|Course\s+(?:No|Code|ID))\s*[:\-–]\s*([A-Z0-9]{4,12})',  # Code: CS501
    ]
    for pat in patterns:
        for m in re.finditer(pat, excerpt, re.IGNORECASE):
            candidate = m.group(1).strip().upper().replace(' ', '')
            # Must look like a code (letters + digits, 4-10 chars)
            if re.match(r'^[A-Z]{1,6}\d{3,5}$|^\d{2}[A-Z]{2,4}\d{3,5}$', candidate):
                return candidate

    return ""

def _keyword_difficulty(name):
    n = name.lower()
    if any(k in n for k in _DIFF_5_KW): return 5
    if any(k in n for k in _DIFF_4_KW): return 4
    if any(k in n for k in _DIFF_2_KW): return 2
    if any(k in n for k in _DIFF_1_KW): return 1
    return None






# ─────────────────────────────────────────────────────────────────────────────
# LLM helpers
# ─────────────────────────────────────────────────────────────────────────────

_SYS_ANALYST = (
    "You are an expert educational curriculum analyst. "
    "Your output must be valid JSON only — no markdown, no explanation, no comments."
)

# ── Step 1 prompt: discover all subjects present in the document ──────────────
_IDENTIFY_SUBJECTS_PROMPT = """\
This is a university syllabus document. It may contain ONE or MULTIPLE subjects/courses.

DOCUMENT TEXT (first {chars} chars):
{text}

Identify ALL distinct subjects/courses present in this document.
For each subject, find its precise name as it appears in the document.

Return ONLY valid JSON:
{{
  "subjects": [
    {{
      "name": "Exact subject name as it appears in the document",
      "code": "Course code if present, else empty string",
      "approximate_start_position": "brief phrase from document that marks where this subject starts"
    }}
  ]
}}

Rules:
- Only include actual academic subjects/courses (e.g., "Machine Learning", "Data Structures")
- Do NOT include: department names, college names, regulation codes, headers, footers
- If only one subject exists in the document, return that one subject
- Maximum 20 subjects
"""

# ── Step 2 prompt: deep extraction for one subject section ───────────────────
_EXTRACT_SUBJECT_PROMPT = """\
Extract the complete curriculum structure from this syllabus section for the subject "{subject}".

SYLLABUS SECTION TEXT:
{text}

Return ONLY valid JSON with this EXACT structure:
{{
  "subject_name": "{subject}",
  "subject_code": "code or empty string",
  "overview": "1-2 sentence description of what students will learn",
  "units": [
    {{
      "unit_name": "Unit I: Introduction to ...",
      "unit_number": 1,
      "topics": [
        {{
          "name": "Exact topic name from syllabus",
          "difficulty": 3,
          "est_hours": 2.0,
          "prerequisites": ["Other Topic Name from THIS subject only"],
          "key_concepts": ["concept1", "concept2"],
          "is_foundational": false
        }}
      ]
    }}
  ],
  "recommended_start_order": ["Topic1", "Topic2", "Topic3", "Topic4", "Topic5"]
}}

STRICT RULES:
- Extract ONLY topics explicitly listed in the syllabus text — do not invent topics
- Each topic name must be a real academic concept, NOT: page numbers, credits, L/T/P/C values,
  regulation codes, teacher names, exam patterns, book titles, institution names, or table headers
- Unit names must come from the document (Unit I, Module 2, Chapter 3, etc.)
- difficulty: 1=very easy, 2=basic, 3=intermediate, 4=hard, 5=advanced
- est_hours: realistic study hours for a single topic (0.5 to 5.0)
- prerequisites: ONLY topic names listed in this same subject
- is_foundational: true if mastering this unlocks many other topics
- recommended_start_order: first 5 topics a student should study
- If no clear unit structure exists, use "Course Topics" as a single unit name
"""

_CROSS_SUBJECT_PROMPT = """\
A student is studying these subjects simultaneously:

{subjects_summary}

Identify topics that share foundational knowledge or concepts across subjects.
Example: NLP "Attention Mechanism" and NNDL "Self-Attention" share knowledge.

Return ONLY JSON:
{{
  "relations": [
    {{
      "subject_a": "NLP",
      "topic_a": "Attention Mechanism",
      "subject_b": "NNDL",
      "topic_b": "Self-Attention in Transformers",
      "relation": "foundation"
    }}
  ]
}}

relation types: "foundation" (A is required knowledge for B), "similar" (same concept different framing), "dependent" (knowing A makes B easier)
Only list clear, meaningful relationships — not superficial ones.
"""


async def _llm_json(prompt: str, timeout: float = 90.0) -> Optional[dict]:
    """Send a prompt to Ollama and parse JSON from the response."""
    if not await _is_ollama_reachable():
        return None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": GEN_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYS_ANALYST},
                        {"role": "user",   "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.05, "num_predict": 2048},
                },
                timeout=timeout,
            )
            if r.status_code != 200:
                logger.debug("Ollama returned %s", r.status_code)
                return None

            content = r.json().get("message", {}).get("content", "")

            # Try direct parse
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

            # Try extract from fenced block ```json ... ```
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

            # Try outermost { ... }
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

    except Exception as exc:
        logger.debug("LLM call failed: %s", exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (when Ollama is unavailable or returns bad JSON)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_subject_section(text: str, subject: str, subject_code: str = "") -> str:
    """Find the section of a multi-course document that belongs to *subject*.

    Handles diverse syllabus formats from universities worldwide:
      - Indian university booklets: multiple courses with "(CODE) COURSE TITLE" + "TEACHING SCHEME"
      - US/UK semester syllabi: "Week 1:", "Week 2:" blocks
      - Module/Unit/Chapter numbered sections
      - Any document with repeated section boundary markers

    Returns the text of the matching section, or the full document if no
    section markers are detected.
    """
    # Build keyword list from subject name
    stop_words = {
        "and", "or", "of", "the", "a", "an", "in", "for", "to", "with",
        "course", "lab", "laboratory",
    }
    key_words = [
        w for w in re.findall(r"[a-z]+", subject.lower())
        if len(w) > 3 and w not in stop_words
    ]
    if not key_words:
        return text
    min_score = max(1, len(key_words) // 2)

    # ── Strategy 1: Indian university "TEACHING SCHEME" booklets ─────────
    # Each course has "(CODE) COURSE TITLE\n...\nTEACHING SCHEME" header.
    # We locate the TEACHING SCHEME occurrence whose preceding window contains
    # an EXACT title match (or course-code match) for *subject*.
    ts_positions = [m.start() for m in re.finditer(r"TEACHING\s+SCHEME", text, re.IGNORECASE)]
    if len(ts_positions) >= 2:
        course_title_re = re.compile(
            r"\(([A-Z0-9]{6,14})\)\s+([A-Z][A-Z\s&/\-]+?)(?:\n|\r|\Z)",
            re.MULTILINE,
        )
        subj_upper = subject.upper().strip()      # "COMPUTER NETWORKS"
        code_upper = subject_code.upper().strip() # "22PC1IN202"

        for i, pos in enumerate(ts_positions):
            window = text[max(0, pos - 600): pos]
            title_match = course_title_re.search(window)
            if not title_match:
                continue
            found_code = title_match.group(1).strip()
            found_title = title_match.group(2).strip()

            # Exact code match — highest confidence
            code_hit = code_upper and found_code == code_upper
            # Exact title match (normalised to uppercase)
            title_hit = found_title == subj_upper
            # Soft: all key_words present in found title
            kw_hit = all(kw in found_title.lower() for kw in key_words) if key_words else False

            if code_hit or title_hit or kw_hit:
                section_start = max(0, pos - 600)
                section_end = (
                    ts_positions[i + 1] - 600
                    if i + 1 < len(ts_positions)
                    else len(text)
                )
                section_end = max(section_start + 500, section_end)
                logger.debug(
                    "Section for '%s' found at TS pos=%d len=%d (code_hit=%s title_hit=%s kw_hit=%s)",
                    subject, pos, section_end - section_start, code_hit, title_hit, kw_hit,
                )
                return text[section_start:section_end]

    # ── Strategy 2: Generic repetitive section boundaries ────────────────
    # Find patterns like "Module 1:" / "Week 1:" / "Chapter 1:" etc.
    boundary_re = re.compile(
        r"^(?:module|unit|chapter|week|lecture|topic|section|part|lab)\s*[-–]?\s*\d+",
        re.IGNORECASE | re.MULTILINE,
    )
    boundaries = [m.start() for m in boundary_re.finditer(text)]
    if len(boundaries) >= 3:
        # Check if this document appears to contain MULTIPLE subjects
        # (heading count > 20 usually means a multi-subject booklet)
        if len(boundaries) <= 20:
            # Few sections → whole document is one subject
            return text
        # Many sections: select those whose neighbourhood matches subject keywords
        matching: list[str] = []
        for i, pos in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            block = text[pos:end]
            score = sum(1 for kw in key_words if kw in block.lower())
            if score >= min_score:
                matching.append(block)
        if matching:
            return "\n\n".join(matching)

    # ── Strategy 3: Subject heading search ────────────────────────────────
    # Look for a line containing the subject name as a heading
    subject_re = re.compile(
        r"^[\s\-=_#*]*" + re.escape(subject) + r"[\s\-=_#*]*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = subject_re.search(text)
    if m:
        start = m.start()
        # Return 8000 chars from the subject heading
        return text[start: start + 8000]

    # ── Fallback: full text ────────────────────────────────────────────────
    return text


def _parse_unit_topics(block: str) -> list[str]:
    """Extract individual topic names from a unit description block.

    Indian university syllabi list topics as comma/dash-separated phrases inside
    paragraph-style paragraphs (long lines), e.g.:
      "UNIT-I:\\nIntroduction: AI problems, intelligent agents, problem formulation."

    Strategy:
      1. Strip the unit header line(s).
      2. Recombine the remaining paragraph text.
      3. Remove textbook / reference cruft.
      4. Split on commas, semicolons, and dashes.
      5. Clean and deduplicate each fragment.
    """
    from app.core.syllabus_processing import _is_junk_line

    # ── 1. Split into lines, separate header from body ────────────────────────
    raw_lines = [l.strip() for l in block.strip().splitlines()]
    body_lines: list[str] = []
    in_header = True
    # Match "UNIT-I:", "UNIT-I: Introduction to ML", "Module 2:", "Chapter 3 - Title" etc.
    unit_header_re = re.compile(
        r"^(?:unit|module|chapter|section|part|lecture|lab|week)\s*[-–]?\s*(?:\d+|[IVX]+)[:\s.–-]*",
        re.IGNORECASE,
    )
    for line in raw_lines:
        if in_header and unit_header_re.match(line):
            # Strip the unit marker prefix from this line — rest is unit title, not a topic
            # e.g. "UNIT-I: Introduction to ML" → skip entire line (title, not topic content)
            # e.g. "UNIT-I:" alone → skip
            in_header = False  # everything AFTER this line is body
            continue
        in_header = False
        body_lines.append(line)

    body = " ".join(body_lines)

    # ── 2. Remove boilerplate sections (textbooks, references, URLs) ──────────
    body = re.sub(
        r"\b(TEXT\s*BOOKS?|REFERENCES?|ONLINE\s*RESOURCES?)\s*:?[\s\S]*",
        "", body, flags=re.IGNORECASE,
    )
    body = re.sub(r"https?://\S+", "", body)
    # Remove "(N Hrs)" annotations
    body = re.sub(r"\(\d+\s*Hrs?\)", "", body, flags=re.IGNORECASE)

    # ── 3. Comma / semicolon / dash split ─────────────────────────────────────
    # Also split on " - " and " – " (em dash as topic separator in Indian syllabi)
    parts = re.split(r"[;,]| – | - |\n", body)

    seen: set[str] = set()
    topics: list[str] = []

    for part in parts:
        # Strip bullets, numbering, leading/trailing punctuation
        part = re.sub(r"^\s*[\d]+\.\s*", "", part)
        part = part.strip(" .,;:–-•◦▪\t")
        # Remove trailing parenthetical like "(Heuristic search)"
        part = re.sub(r"\s*\([^)]{0,30}\)\s*$", "", part).strip()
        # Skip very short or very long fragments
        # Allow short acronyms (SVM, CNN, KNN) — minimum 2 chars
        if len(part) < 2 or len(part) > 100:
            continue
        # Capitalise first letter
        if part and part[0].islower():
            part = part[0].upper() + part[1:]
        key = re.sub(r"\s+", " ", part.lower()).strip()
        if key not in seen and not _is_junk_line(part):
            seen.add(key)
            topics.append(part)

    if topics:
        return topics

    # ── 4. Last resort: return first non-empty line as topic ──────────────────
    return [raw_lines[0][:80]] if raw_lines else ["Unit content"]


def _rule_based_analysis(text: str, subject: str) -> dict:
    """Produce a structured analysis without LLM — uses heuristics.

    Supports diverse syllabus formats:
      - Indian university (UNIT-I:, UNIT-II: with Roman numerals)
      - US/UK style (Week 1:, Week 2: / Lecture 1:, Lecture 2:)
      - Generic numbered (Module 1:, Chapter 1:, Section 1:)
      - Learning Objective based (CO1:, LO1:, CLO1:)
      - Flat numbered list (1., 2., 3. ...)
    """
    from app.core.syllabus_processing import split_into_topics

    # Narrow down to just the relevant course section (handles multi-course PDFs)
    section_text = _extract_subject_section(text, subject)

    raw_topics = split_into_topics(section_text)
    if not raw_topics:
        raw_topics = [f"{subject} Topic {i+1}" for i in range(5)]

    total = len(raw_topics)

    # ── Universal unit/section header detection ───────────────────────────
    # Supports: UNIT-I:  Unit 1:  Week 1:  Lecture 2:  Chapter 3:
    #           Module-I:  Topic 1:  Part 1:  Section 1:
    #           CO1: CLO1: LO1: (learning objective headers)
    unit_re = re.compile(
        r"^(?:"
        r"(?:unit|module|chapter|section|part|week|lecture|lab|topic)\s*[-–]?\s*(?:\d+|[IVX]+)"
        r"|(?:co|clo|lo|po)\s*\d+"           # course/learning outcome headers
        r")[:\s.]+",
        re.IGNORECASE | re.MULTILINE,
    )
    unit_matches = list(unit_re.finditer(section_text))

    # ── Also try "--- Slide N ---" format (exported PPTX) ─────────────────
    if not unit_matches:
        slide_re = re.compile(r"^---\s*Slide\s+(\d+)\s*---", re.IGNORECASE | re.MULTILINE)
        unit_matches = list(slide_re.finditer(section_text))

    # ── Build unit → topics mapping ───────────────────────────────────────
    units_out: list[dict] = []
    if unit_matches:
        for ui, um in enumerate(unit_matches):
            end = unit_matches[ui + 1].start() if ui + 1 < len(unit_matches) else len(section_text)
            block = section_text[um.start():end]
            block_topics = _parse_unit_topics(block)
            if block_topics:
                # Build a readable unit name: use the full first line of the block
                # e.g. "UNIT-I: Introduction to ML" → unit_name = "Unit I: Introduction to ML"
                first_line = block.split("\n")[0].strip()[:80]
                units_out.append({
                    "unit_name": first_line,
                    "unit_number": ui + 1,
                    "topics": block_topics,
                })
    
    if not units_out:
        # No unit headings — one flat unit
        units_out = [{"unit_name": "Course Topics", "unit_number": 1, "topics": raw_topics}]

    # ── Assign difficulty per topic ───────────────────────────────────────
    processed = 0
    units_result = []
    for u in units_out:
        topic_dicts = []
        for tname in u["topics"]:
            ratio = processed / max(1, total)
            kw_diff = _keyword_difficulty(tname)
            if kw_diff:
                diff = kw_diff
            else:
                diff = max(1, min(5, 1 + int(ratio * 4)))
            topic_dicts.append({
                "name": tname,
                "difficulty": diff,
                "est_hours": DIFFICULTY_HOURS[diff],
                "prerequisites": [],
                "key_concepts": [],
                "is_foundational": ratio < 0.15,
            })
            processed += 1
        units_result.append({
            "unit_name": u["unit_name"],
            "unit_number": u["unit_number"],
            "topics": topic_dicts,
        })

    return {
        "subject_name": subject,
        "subject_code": _extract_subject_code(section_text, subject),
        "overview": f"Course materials for {subject}.",
        "units": units_result,
        "recommended_start_order": raw_topics[:5],
        "_fallback": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis entry point — single subject
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_syllabus(text: str, subject: str) -> dict:
    """Analyze a syllabus section for one subject.

    Uses LLM with a large text budget; falls back to rule-based analysis.
    The enriched output contains per-topic difficulty, estimated study hours,
    prerequisite chains, and key concepts — driving the intelligent scheduler.
    """
    if not text or len(text.strip()) < 50:
        return _rule_based_analysis(text or "", subject)

    # Use a bounded excerpt to keep latency low on large documents.
    excerpt = text[:LLM_SUBJECT_EXCERPT_CHARS].strip()
    prompt = _EXTRACT_SUBJECT_PROMPT.format(subject=subject, text=excerpt)
    result = await _llm_json(prompt, timeout=LLM_SUBJECT_TIMEOUT_SEC)

    if result and isinstance(result.get("units"), list) and result["units"]:
        result.setdefault("subject_name", subject)
        result.setdefault("subject_code", _extract_subject_code(text, subject))
        result.setdefault("overview", f"Course materials for {subject}.")
        # Normalize and enrich each topic
        for unit in result["units"]:
            for t in unit.get("topics", []):
                if not isinstance(t, dict):
                    continue
                diff = int(t.get("difficulty", 3))
                diff = max(1, min(5, diff))
                t["difficulty"] = diff
                t.setdefault("est_hours", DIFFICULTY_HOURS[diff])
                t.setdefault("prerequisites", [])
                t.setdefault("key_concepts", [])
                t.setdefault("is_foundational", False)
                t["subject"] = result["subject_name"]
                t["unit"] = unit.get("unit_name", "")
        return result

    logger.info("LLM analysis failed for '%s', using rule-based fallback", subject)
    return _rule_based_analysis(text, subject)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-subject identification — for syllabi containing many courses
# ─────────────────────────────────────────────────────────────────────────────

async def identify_subjects_in_document(text: str) -> list[dict]:
    """Pass 1: ask the LLM to list all subjects present in the document.

    Returns a list of dicts: {name, code, approximate_start_position}
    Falls back to heuristic detection if LLM fails.
    """
    if not text or len(text.strip()) < 100:
        return []

    # Very large multi-course PDFs are faster and more reliable with structure
    # heuristics than a huge first-pass LLM call.
    if len(text) >= LARGE_DOC_CHAR_THRESHOLD:
        subjects = _heuristic_identify_subjects(text)
        if subjects:
            logger.info(
                "Large document (%d chars): heuristic identified %d subjects",
                len(text), len(subjects),
            )
            return subjects

    # Use first 8000 chars for subject identification — enough for a TOC or header block
    chars = min(8000, len(text))
    excerpt = text[:chars].strip()
    prompt = _IDENTIFY_SUBJECTS_PROMPT.format(text=excerpt, chars=chars)
    result = await _llm_json(prompt, timeout=LLM_IDENTIFY_TIMEOUT_SEC)

    if result and isinstance(result.get("subjects"), list):
        valid = []
        for s in result["subjects"]:
            if not isinstance(s, dict):
                continue
            name = (s.get("name") or "").strip()
            if name and len(name) >= 3:
                valid.append({
                    "name": name,
                    "code": (s.get("code") or "").strip(),
                    "anchor": (s.get("approximate_start_position") or "").strip(),
                })
        if valid:
            logger.info("LLM identified %d subjects in document", len(valid))
            return valid

    # Heuristic fallback: look for repeated UNIT/MODULE blocks as subject boundaries
    return _heuristic_identify_subjects(text)


def _heuristic_identify_subjects(text: str) -> list[dict]:
    """Identify subject blocks using structural heuristics (no LLM).

    Runs ALL applicable patterns and merges results (Format-2 entries take
    precedence over Format-1 when both find the same code).

      1. Table format: code on own line, title on next line (VNR/JNTUH R22 style)
      2. Inline format: (CODE) COURSE TITLE on same line (detail-section headers)
      3. Multiple "UNIT-I" resets as subject boundary markers
    """
    scan_text = text[:50000]  # course and detail listings span the first ~40 000 chars

    _SKIP = {"laboratory", "lab", "internship", "gender sensitization",
             "ancient wisdom", "communication skills", "college", "university",
             "department", "regulation", "total"}

    def _should_skip(name: str) -> bool:
        nl = name.lower()
        return any(x in nl for x in _SKIP)

    # ── Format 1: course table rows ──────────────────────────────────────────
    # "22PC1IN202 \nComputer Networks \n3 \n0 \n0 \n3 \n3"
    table_re = re.compile(
        r"^(\d{2}[A-Z]{2,4}\d[A-Z]{2}\d{2,4})\s*\n"   # exact course-code line
        r"([^\n]{4,80}?)\s*\n"                           # title on next line
        r"(?:\d[\n\s]*){3,}",                             # L T P credit numbers
        re.MULTILINE,
    )
    f1: dict[str, dict] = {}                             # code → entry
    for m in table_re.finditer(scan_text):
        code = m.group(1).upper()
        raw = m.group(2).strip()
        if not raw or _should_skip(raw):
            continue
        name = raw.title() if raw.isupper() else raw
        if len(name) >= 4 and code not in f1:
            f1[code] = {"name": name, "code": code, "anchor": f"{code}: {name[:50]}"}

    # ── Format 2: (CODE) COURSE TITLE detail-section headers ─────────────────
    # "(22PC1IN202) COMPUTER NETWORKS\n\nTEACHING SCHEME"
    code_title_re = re.compile(
        r"\(([A-Z0-9]{6,12})\)\s+([A-Z][A-Z\s&/\-,]{4,70}?)(?:\n|\r|$)",
        re.MULTILINE,
    )
    f2: dict[str, dict] = {}
    for m in code_title_re.finditer(scan_text):
        code = m.group(1).strip()
        raw = m.group(2).strip()
        if not raw or _should_skip(raw):
            continue
        name = raw.title()
        if len(name) >= 4 and code not in f2:
            f2[code] = {"name": name, "code": code, "anchor": m.group(0)[:60]}

    # ── Merge: Format-2 is more reliable (full title from detail section) ────
    # Start with F1 entries, then add/overwrite with F2 entries.
    merged: dict[str, dict] = {**f1, **f2}

    if merged:
        subjects = list(merged.values())
        logger.info(
            "Heuristic identified %d subjects (F1=%d, F2=%d, merged=%d)",
            len(subjects), len(f1), len(f2), len(merged),
        )
        return subjects

    # ── Format 3: Multiple "UNIT-I" resets ── subject boundary markers ────────
    subjects: list[dict] = []
    seen_codes: set[str] = set()

    unit_re = re.compile(r"^UNIT[-\s]*I[:\s]", re.IGNORECASE | re.MULTILINE)
    unit_one_positions = [m.start() for m in unit_re.finditer(text)]

    if len(unit_one_positions) > 1:
        for pos in unit_one_positions:
            window = text[max(0, pos - 600):pos]
            lines_w = [l.strip() for l in window.splitlines() if l.strip()]
            if lines_w:
                candidate = lines_w[-1]
                if (4 < len(candidate) < 80 and
                        not re.fullmatch(r"[\d\s\.\-\|/:,;()]+", candidate)):
                    if candidate not in seen_codes:
                        seen_codes.add(candidate)
                        subjects.append({"name": candidate, "code": "", "anchor": candidate[:60]})

    if subjects:
        logger.info("Format-3 heuristic identified %d subjects", len(subjects))
    return subjects


async def analyze_full_syllabus_document(text: str, hint_subject: str = "") -> list[dict]:
    """Full pipeline: identify all subjects, extract topics for each.

    Returns a list of subject-analysis dicts (same shape as analyze_syllabus()).
    If only one subject is found, returns [analyze_syllabus(text, subject)].
    """
    if not text or len(text.strip()) < 100:
        if hint_subject:
            return [_rule_based_analysis(text or "", hint_subject)]
        return []

    # ── Pass 1: identify subjects ────────────────────────────────────────────
    subjects = await identify_subjects_in_document(text)

    if not subjects:
        # Single-subject document
        name = hint_subject or "Course"
        logger.info("No multiple subjects detected — treating as single subject: %s", name)
        result = await analyze_syllabus(text, name)
        return [result]

    if len(subjects) == 1:
        name = subjects[0]["name"] or hint_subject or "Course"
        result = await analyze_syllabus(text, name)
        return [result]

    # ── Pass 2: extract per-subject section + analyse ────────────────────────
    # Hybrid mode for speed: use LLM for first N subjects, rule-based for the rest.
    llm_budget = max(0, min(MAX_LLM_SUBJECTS_PER_DOC, len(subjects)))
    if len(subjects) > llm_budget:
        logger.info(
            "Large multi-subject doc: hybrid analysis (subjects=%d, llm_budget=%d)",
            len(subjects), llm_budget,
        )

    sem = asyncio.Semaphore(max(1, SUBJECT_ANALYSIS_CONCURRENCY))

    async def _analyze_subject(idx: int, subj_info: dict) -> Optional[dict]:
        subj_name = subj_info["name"]
        subj_code = subj_info.get("code", "")
        section = _extract_subject_section(text, subj_name, subject_code=subj_code)
        if len(section.strip()) < 100:
            logger.debug("Skipping subject '%s': section too short", subj_name)
            return None

        use_llm = idx < llm_budget
        if use_llm:
            async with sem:
                analysis = await analyze_syllabus(section, subj_name)
        else:
            analysis = _rule_based_analysis(section, subj_name)

        if subj_code and not analysis.get("subject_code"):
            analysis["subject_code"] = subj_code

        logger.info(
            "Extracted subject '%s' via %s: %d units, %d topics",
            subj_name,
            "LLM" if use_llm else "rules",
            len(analysis.get("units", [])),
            sum(len(u.get("topics", [])) for u in analysis.get("units", [])),
        )
        return analysis

    jobs = [_analyze_subject(i, subj) for i, subj in enumerate(subjects)]
    analyses: list[dict] = []
    results = await asyncio.gather(*jobs, return_exceptions=True)
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Subject analysis job failed: %s", res)
            continue
        if res:
            analyses.append(res)

    if not analyses and hint_subject:
        analyses = [_rule_based_analysis(text, hint_subject)]

    return analyses


# ─────────────────────────────────────────────────────────────────────────────
# Cross-subject relationship detection
# ─────────────────────────────────────────────────────────────────────────────

async def find_cross_subject_relations(analyses: list[dict]) -> list[dict]:
    """Ask LLM to find conceptual bridges between topics across subjects.

    E.g. "NLP: Attention Mechanism" ↔ "NNDL: Self-Attention in Transformers"
    These pairs get scheduled in nearby days so students see the connection.
    """
    if len(analyses) < 2:
        return []

    parts = []
    for a in analyses:
        topics = [t["name"] for u in a.get("units", []) for t in u.get("topics", [])]
        parts.append(f"Subject: {a['subject_name']}\nTopics: {', '.join(topics[:30])}")

    prompt = _CROSS_SUBJECT_PROMPT.format(subjects_summary="\n\n".join(parts))
    result = await _llm_json(prompt, timeout=60.0)

    if result and isinstance(result.get("relations"), list):
        return result["relations"]

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python topological sort (Kahn's algorithm)
# ─────────────────────────────────────────────────────────────────────────────

def _topological_sort(topics: list[dict]) -> list[dict]:
    """Sort a flat list of topics respecting their prerequisite dependencies.

    Uses Kahn's algorithm on the prerequisite DAG:
      - Topics with no prerequisites, sorted foundational-first then difficulty-asc, go first.
      - As prerequisites are resolved, dependents are enqueued in difficulty-asc order.
      - Any cycles (LLM hallucinated circular deps) are broken; remaining topics appended.
    """
    name_to_topic = {t["name"]: t for t in topics}

    # in_degree[name] = number of unresolved prerequisites
    in_degree: dict[str, int] = {t["name"]: 0 for t in topics}
    # dependents[name] = list of topic names that have this as a prerequisite
    dependents: dict[str, list[str]] = defaultdict(list)

    for t in topics:
        for pre in t.get("prerequisites", []):
            if pre in name_to_topic and pre != t["name"]:
                dependents[pre].append(t["name"])
                in_degree[t["name"]] += 1

    # Seed queue with topics that have zero unresolved prerequisites
    ready = sorted(
        [t for t in topics if in_degree[t["name"]] == 0],
        key=lambda t: (0 if t.get("is_foundational") else 1, t.get("difficulty", 3)),
    )
    queue: deque[dict] = deque(ready)

    result: list[dict] = []
    while queue:
        t = queue.popleft()
        result.append(t)
        # Unblock dependents
        for dep_name in sorted(
            dependents[t["name"]],
            key=lambda n: name_to_topic[n].get("difficulty", 3),
        ):
            in_degree[dep_name] -= 1
            if in_degree[dep_name] == 0:
                queue.append(name_to_topic[dep_name])

    # Append remaining (cycle remnants or unknown prerequisites)
    placed = {t["name"] for t in result}
    for t in sorted(topics, key=lambda t: t.get("difficulty", 3)):
        if t["name"] not in placed:
            result.append(t)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Intelligent schedule generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_intelligent_schedule(
    analyses: list[dict],
    *,
    hours_per_day: float = 3.0,
    num_days: int = 30,
    subject_priorities: dict[str, int] | None = None,
    cross_subject_relations: list[dict] | None = None,
    user_overrides: dict[str, dict] | None = None,
    study_start_hour: int = 9,
    study_end_hour: int = 23,
) -> dict:
    """Generate an ordered, difficulty-aware, cross-subject study schedule.

    Algorithm overview:
      1. For each subject: apply topological sort over the prerequisite DAG
         → topics come out in a valid learning order (easy/foundational first).
      2. Assign time per topic = DIFFICULTY_HOURS[diff] + any user override.
      3. Build a priority-weighted round-robin interleaving of subjects so all
         subjects progress in parallel (not "finish NLP, then NNDL").
      4. Place topic blocks into daily slots, respecting hours_per_day.
      5. Cross-subject related-topic pairs are bumped to adjacent days when
         detected (best-effort; doesn't break ordering constraints).
      6. Unscheduled topics (schedule filled before all topics placed) are
         appended with extended dates so the full curriculum is always shown.
    """
    subject_priorities = subject_priorities or {}
    
    # Build time slots within user's study window
    time_slots = build_time_slots(study_start_hour, study_end_hour)
    cross_subject_relations = cross_subject_relations or []
    user_overrides = user_overrides or {}

    if not analyses:
        return {"schedule": [], "summary": {}}

    today = date.today()

    # ── Per-subject ordered topic lists ──────────────────────────────────────
    subj_ordered: list[tuple[str, str, list[dict]]] = []
    for analysis in analyses:
        subj = analysis.get("subject_name", "Unknown")
        subj_code = analysis.get("subject_code", "")
        flat: list[dict] = []
        for unit in analysis.get("units", []):
            for t in unit.get("topics", []):
                flat.append({**t, "subject": subj, "subject_code": subj_code, "unit": unit.get("unit_name", ""), "unit_number": unit.get("unit_number", 0)})
        if not flat:
            continue
        ordered = _topological_sort(flat)
        subj_ordered.append((subj, subj_code, ordered))

    if not subj_ordered:
        return {"schedule": [], "summary": {}}

    # Sort subjects: higher priority (lower number) → more weight in interleave
    subj_ordered.sort(key=lambda x: subject_priorities.get(x[0], 5))

    # ── Cross-subject related topic pairs → prefer adjacent days ─────────────
    # Build a set of (topic_a, topic_b) pairs
    related_pairs: set[tuple[str, str]] = set()
    for rel in cross_subject_relations:
        ta, tb = rel.get("topic_a", ""), rel.get("topic_b", "")
        if ta and tb:
            related_pairs.add((ta, tb))
            related_pairs.add((tb, ta))

    # ── Priority-weighted round-robin interleave sequence ────────────────────
    weights = [max(1, 6 - subject_priorities.get(s[0], 3)) for s in subj_ordered]
    natural: list[int] = []
    remaining_w = list(weights)
    total_w = sum(remaining_w)
    for _ in range(total_w):
        idx = max(range(len(remaining_w)), key=lambda i: remaining_w[i])
        natural.append(idx)
        remaining_w[idx] -= 1
    interleave_seq = natural

    # ── Schedule generation ───────────────────────────────────────────────────
    pointers = [0] * len(subj_ordered)
    schedule: list[dict] = []
    task_id = 1
    current_day = today
    seq_pos = 0
    day_num = 0
    total_topics = sum(len(t[2]) for t in subj_ordered)
    placed = 0

    while day_num < num_days and placed < total_topics:
        daily_hours_remaining = hours_per_day
        slot_idx = 0

        while daily_hours_remaining > 0.25 and slot_idx < len(TIME_SLOTS):
            # Pick next subject with topics remaining
            found = False
            for attempt in range(len(subj_ordered)):
                s_idx = interleave_seq[seq_pos % len(interleave_seq)]
                seq_pos += 1
                if pointers[s_idx] < len(subj_ordered[s_idx][2]):
                    found = True
                    break

            if not found:
                break

            subj_name, subj_code, topics = subj_ordered[s_idx]
            t = topics[pointers[s_idx]]
            pointers[s_idx] += 1
            placed += 1

            diff = int(t.get("difficulty", 3))
            diff = max(1, min(5, diff))
            base_h = float(t.get("est_hours", DIFFICULTY_HOURS[diff]))
            override_h = float(user_overrides.get(t["name"], {}).get("extra_hours", 0.0))
            total_h = base_h + override_h

            duration_str = (
                f"{total_h:.0f}h" if total_h >= 1.0 else f"{int(total_h * 60)}min"
            )

            schedule.append({
                "id": task_id,
                "date": current_day.isoformat(),
                "time": TIME_SLOTS[slot_idx % len(TIME_SLOTS)],
                "subject": subj_name,
                "subject_code": subj_code,
                "unit": t.get("unit", ""),
                "unit_number": t.get("unit_number", 0),
                "topic": t["name"],
                "difficulty": diff,
                "difficultyLabel": DIFFICULTY_LABEL[diff],
                "estimated_hours": round(total_h, 1),
                "duration": duration_str,
                "key_concepts": t.get("key_concepts", []),
                "is_foundational": t.get("is_foundational", False),
                "status": "pending",
            })
            task_id += 1

            daily_hours_remaining -= total_h
            slot_idx += 1

        current_day += timedelta(days=1)
        day_num += 1

    # Append any remaining topics (beyond num_days) with extended dates
    for s_idx, (subj_name, subj_code, topics) in enumerate(subj_ordered):
        while pointers[s_idx] < len(topics):
            t = topics[pointers[s_idx]]
            pointers[s_idx] += 1
            diff = int(t.get("difficulty", 3))
            diff = max(1, min(5, diff))
            total_h = float(t.get("est_hours", DIFFICULTY_HOURS[diff]))
            schedule.append({
                "id": task_id,
                "date": current_day.isoformat(),
                "time": TIME_SLOTS[0],
                "subject": subj_name,
                "subject_code": subj_code,
                "unit": t.get("unit", ""),
                "unit_number": t.get("unit_number", 0),
                "topic": t["name"],
                "difficulty": diff,
                "difficultyLabel": DIFFICULTY_LABEL[diff],
                "estimated_hours": round(total_h, 1),
                "duration": f"{total_h:.0f}h" if total_h >= 1.0 else f"{int(total_h*60)}min",
                "key_concepts": t.get("key_concepts", []),
                "is_foundational": t.get("is_foundational", False),
                "status": "pending",
            })
            task_id += 1
            current_day += timedelta(days=1)

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(schedule)
    avg_diff = sum(t["difficulty"] for t in schedule) / max(1, total)
    by_subj = defaultdict(int)
    for t in schedule:
        by_subj[t["subject"]] += 1

    return {
        "schedule": schedule,
        "summary": {
            "totalTopics": total,
            "averageDifficulty": round(avg_diff, 1),
            "bySubject": dict(by_subj),
            "startDate": today.isoformat(),
            "endDate": (today + timedelta(days=max(num_days, total))).isoformat(),
            "crossSubjectRelations": len(cross_subject_relations),
        },
    }

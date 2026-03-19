"""LLM-powered meaningful topic extraction from raw document text.

Removes junk (URLs, book titles, boilerplate) and extracts only meaningful
learning concepts using the LLM.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "llama3.2:1b")


_TOPIC_EXTRACTION_PROMPT = """\
Extract ONLY meaningful academic/learning topics from this raw document text. 
Remove ALL junk: URLs, book titles, author names, copyright notices, institutional names, form fields.

DOCUMENT TEXT (first 3000 chars):
{text}

Return ONLY valid JSON with no markdown or code blocks:
{{
  "topics": [
    "Topic 1 name (actual learning concept)",
    "Topic 2 name",
    "..."
  ]
}}

Guidelines:
- Topics must be actual learning concepts (e.g., "Data Structures", "Networking Protocols")
- Remove: URLs, email addresses, book/movie titles with authors, ISBN codes, dates
- Remove: metadata like "Chapter 1", "Section 2.3", "Page 45", "©2023"
- Remove: institution names, department names, "Syllabus Review", "Course Overview"
- Keep: "TCP/IP Fundamentals", "Machine Learning Algorithms", "Distributed Systems"
- Maximum 200 topics
- Sort by approximate learning order (foundational first)
"""


async def _llm_json(prompt: str, timeout: float = 60.0) -> Optional[dict]:
    """Send a prompt to Ollama and parse JSON from the response."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": GEN_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                },
            )
            if r.status_code != 200:
                logger.warning("Ollama returned %s: %s", r.status_code, r.text[:200])
                return None
            data = r.json()
            content = data.get("message", {}).get("content", "").strip()
            if not content:
                return None
            # Try to extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
    except Exception as e:
        logger.warning("LLM JSON call failed: %s", e)
        return None


async def extract_meaningful_topics(text: str, max_topics: int = 200) -> List[str]:
    """Extract meaningful topics using LLM, filtering out junk.
    
    Falls back to basic regex extraction if LLM unavailable.
    """
    if not text or len(text.strip()) < 100:
        return []
    
    # Try LLM extraction first
    excerpt = text[:3000].strip()
    prompt = _TOPIC_EXTRACTION_PROMPT.format(text=excerpt)
    result = await _llm_json(prompt, timeout=60.0)
    
    if result and isinstance(result.get("topics"), list):
        topics = result.get("topics", [])
        # Filter empty strings and deduplicate while preserving order
        seen = set()
        clean = []
        for t in topics:
            if isinstance(t, str):
                t = t.strip()
                key = t.lower()
                if t and key not in seen and len(t) >= 3 and len(t) <= 150:
                    seen.add(key)
                    clean.append(t)
                    if len(clean) >= max_topics:
                        break
        if clean:
            logger.info("LLM extraction succeeded: %s meaningful topics", len(clean))
            return clean
    
    logger.warning("LLM extraction failed, using fallback regex-based extraction")
    return _fallback_extract_topics(text, max_topics)


def _fallback_extract_topics(text: str, max_topics: int = 200) -> List[str]:
    """Fallback regex-based extraction for when LLM is unavailable."""
    # Filter out junk patterns
    junk_patterns = [
        r"^https?://",  # URLs
        r"^.*@.*\.",    # Email
        r"^©\s*\d+",    # Copyright
        r"^\d{10,}",    # ISBN-like
        r"^(Chapter|Section|Unit|Lecture|Week|Page|Copyright|Syllabus|Course Overview|Prerequisites|Introduction)",
        r"^[A-Z\s\.]+$",  # ALL CAPS
        r"^[\d\s\.\-\|\/\\]+$",  # Pure numbers/punctuation
    ]
    
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    topics = []
    seen = set()
    
    for line in lines:
        # Skip junk
        if any(re.match(p, line, re.IGNORECASE) for p in junk_patterns):
            continue
        
        # Skip if too short or too long
        if len(line) < 5 or len(line) > 150:
            continue
        
        # Skip lines with too many URLs or emails
        if len(re.findall(r"https?://|@", line)) > 0:
            continue
        
        # Skip common institutional boilerplate
        if any(kw in line.lower() for kw in ["department", "college", "university", "school", "institute", "mailto:", "phone"]):
            continue
        
        # Deduplicate
        key = re.sub(r"\s+", " ", line.lower())
        if key not in seen:
            seen.add(key)
            topics.append(line)
            if len(topics) >= max_topics:
                break
    
    logger.info("Fallback extraction: %s topics", len(topics))
    return topics

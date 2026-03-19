"""Content / file-management endpoint with RAG-powered AI study chatbot."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete as sql_delete

from app.core import rag
from app.core.security import get_current_user_dep
from app.core.syllabus_processing import (
    extract_text_from_file, split_into_topics,
    extract_pages_from_file, find_topic_pages,
)
from app.db.models import StudyMaterial, SubjectAnalysis, ScheduledTopic, User
from app.db.session import get_db, AsyncSessionLocal

_log = logging.getLogger(__name__)

# Keep strong references to background tasks so they aren't GC'd before completing
_background_tasks: set = set()


def _fire_and_forget(coro) -> None:
    """Schedule a coroutine as a background task, keeping a strong reference
    so Python's GC doesn't cancel it before it finishes."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _rag_index_bg(*, user_id: int, material_id: int, text: str, subject: str, filename: str) -> None:
    """Index a document in the background using its own DB session."""
    async with AsyncSessionLocal() as db:
        try:
            await rag.index_document(
                user_id=user_id, material_id=material_id,
                text=text, subject=subject, filename=filename, db=db,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("Background RAG indexing failed: %s", exc)


async def _extract_and_update_bg(
    *, material_id: int, file_path: str, subject: str, filename: str, user_id: int
) -> None:
    """Extract text, run AI curriculum analysis, and update DB with intelligent topics + page numbers.

    IMPORTANT: Only syllabus files (kind="syllabus") generate topics used by the schedule.
    Study materials (kind="material") are RAG-indexed for chat help ONLY — their topics
    are stored for reference but never drive the daily schedule.
    """
    import asyncio as _aio
    loop = _aio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, extract_text_from_file, file_path)
    except Exception as exc:
        _log.warning("Background text extraction failed for material %s: %s", material_id, exc)
        return

    # Also extract per-page texts for page-number tracking
    try:
        page_texts = await loop.run_in_executor(None, extract_pages_from_file, file_path)
    except Exception:
        page_texts = {}

    kind = await _get_mat_kind(material_id)

    # ── SYLLABUS files only: full curriculum extraction ──────────────────────
    # Study materials (PDFs/notes/slides) are RAG-indexed for chat ONLY.
    # They do NOT generate topics for the daily schedule.
    topics: list = []
    all_analyses: list = []

    if kind == "syllabus" and text:
        try:
            from app.core.syllabus_intelligence import analyze_full_syllabus_document
            # Full pipeline: identifies ALL subjects, extracts unit→topic hierarchy per subject
            all_analyses = await analyze_full_syllabus_document(text, hint_subject=subject)
            for analysis in all_analyses:
                for unit in analysis.get("units", []):
                    for t in unit.get("topics", []):
                        name = (t.get("name") if isinstance(t, dict) else str(t)).strip()
                        if name and len(name) >= 3:
                            topics.append(name)
            _log.info(
                "Full syllabus extraction for material %s: %d subjects, %d total topics",
                material_id, len(all_analyses), len(topics),
            )
        except Exception as exc:
            _log.warning("Full syllabus extraction failed for material %s: %s", material_id, exc)

        # Rule-based fallback for syllabus if LLM failed
        if not topics and text:
            try:
                from app.core.syllabus_intelligence import _rule_based_analysis
                fallback = _rule_based_analysis(text, subject)
                all_analyses = [fallback]
                for unit in fallback.get("units", []):
                    for t in unit.get("topics", []):
                        name = (t.get("name") if isinstance(t, dict) else str(t)).strip()
                        if name and len(name) >= 3:
                            topics.append(name)
                _log.info("Rule-based fallback for material %s: %d topics", material_id, len(topics))
            except Exception as exc:
                _log.warning("Rule-based fallback also failed for material %s: %s", material_id, exc)

    # Study materials: no topic extraction for scheduling — just store empty list
    # (RAG indexing below handles chat/search purposes)

    # Build topic→page mapping only for syllabus files
    topic_pages: dict = {}
    if topics and page_texts and kind == "syllabus":
        try:
            topic_pages = find_topic_pages(topics, page_texts)
        except Exception as exc:
            _log.debug("Topic page mapping failed: %s", exc)

    # Write topics + topic_pages to study_materials
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(StudyMaterial).where(StudyMaterial.id == material_id)
            )
            mat = result.scalar_one_or_none()
            if mat:
                mat.topics = topics  # empty list for non-syllabus files
                if topic_pages:
                    mat.topic_pages = topic_pages
                await db.commit()
        except Exception as exc:
            _log.warning("Background topic update failed: %s", exc)

    # Persist each subject's structured curriculum analysis separately
    if all_analyses and kind == "syllabus":
        for analysis in all_analyses:
            subj_name = analysis.get("subject_name", subject)
            try:
                async with AsyncSessionLocal() as db2:
                    existing = await db2.execute(
                        select(SubjectAnalysis).where(
                            SubjectAnalysis.material_id == material_id,
                            SubjectAnalysis.subject == subj_name,
                        )
                    )
                    record = existing.scalar_one_or_none()
                    if record:
                        record.analysis_json = analysis
                    else:
                        db2.add(SubjectAnalysis(
                            material_id=material_id, user_id=user_id,
                            subject=subj_name, analysis_json=analysis,
                        ))
                    await db2.commit()
            except Exception as exc:
                _log.debug("Analysis persistence failed for subject '%s' material %s: %s",
                           subj_name, material_id, exc)

        # Create hierarchical ScheduledTopic records (subject → unit → topic)
        try:
            await _create_scheduled_topics(
                material_id=material_id, user_id=user_id,
                analyses=all_analyses, topic_pages=topic_pages,
            )
        except Exception as exc:
            _log.warning("Scheduled topic creation failed for material %s: %s", material_id, exc)

        # Create on-disk folder structure: uploads/{user_id}/syllabus/{subject}/
        # One folder per identified subject for clean organisation
        await _create_subject_folders(user_id=user_id, analyses=all_analyses)

    # RAG indexing — ALL file types (syllabus and materials) for chat help
    if text:
        await _rag_index_bg(
            user_id=user_id, material_id=material_id,
            text=text, subject=subject, filename=filename,
        )




async def _create_scheduled_topics(
    *, material_id: int, user_id: int,
    analyses: list[dict], topic_pages: dict = None,
) -> None:
    """Create hierarchical ScheduledTopic records from analyzed subjects/units/topics.
    
    For each subject → unit → topic, insert a ScheduledTopic record that can be
    scheduled, marked complete, and rescheduled by the scheduler agents.
    """
    if not analyses:
        return

    _DIFF_MAP = {
        1: "Easy",
        2: "Basic",
        3: "Intermediate",
        4: "Hard",
        5: "Advanced",
    }
    
    topic_pages = topic_pages or {}
    
    async with AsyncSessionLocal() as db:
        try:
            # First, delete any existing ScheduledTopic records for this material (refresh)
            await db.execute(
                sql_delete(ScheduledTopic)
                .where(ScheduledTopic.material_id == material_id)
            )
            await db.commit()
        except Exception as exc:
            _log.debug("Failed to clear old ScheduledTopic records: %s", exc)
    
    async with AsyncSessionLocal() as db:
        for analysis in analyses:
            subj_name = analysis.get("subject_name", "Unknown")
            subj_code = analysis.get("subject_code", "")
            units = analysis.get("units", [])
            
            for unit_idx, unit in enumerate(units):
                unit_name = unit.get("unit_name", f"Unit {unit_idx + 1}")
                topics = unit.get("topics", [])
                
                for topic_idx, topic_item in enumerate(topics):
                    # Handle both dict and string topic formats
                    if isinstance(topic_item, dict):
                        topic_name = topic_item.get("name", "")
                        raw_difficulty = topic_item.get("difficulty", "Medium")
                        est_hours = topic_item.get("estimated_hours", 1.0)
                    else:
                        topic_name = str(topic_item).strip()
                        raw_difficulty = "Medium"
                        est_hours = 1.0
                    
                    if not topic_name or len(topic_name) < 3:
                        continue
                    
                    # Find page number from topic_pages mapping
                    page_num = topic_pages.get(topic_name)

                    # Normalize types before DB insert
                    if isinstance(raw_difficulty, (int, float)):
                        difficulty = _DIFF_MAP.get(int(raw_difficulty), "Medium")
                    else:
                        difficulty = str(raw_difficulty or "Medium")

                    try:
                        est_hours = float(est_hours or 1.0)
                    except Exception:
                        est_hours = 1.0

                    try:
                        page_num = int(page_num) if page_num is not None else None
                    except Exception:
                        page_num = None
                    
                    try:
                        scheduled_topic = ScheduledTopic(
                            user_id=user_id,
                            material_id=material_id,
                            subject=subj_name,
                            subject_code=subj_code,
                            unit_name=unit_name,
                            unit_index=unit_idx,
                            topic_name=topic_name,
                            topic_index=topic_idx,
                            page_number=page_num,
                            estimated_hours=est_hours,
                            difficulty=difficulty,
                            status="pending",
                        )
                        db.add(scheduled_topic)
                    except Exception as exc:
                        _log.debug("Failed to create ScheduledTopic for %s::%s::%s: %s",
                                   subj_name, unit_name, topic_name, exc)
            
            try:
                await db.commit()
                _log.info(
                    "Created ScheduledTopic records for material %s, subject '%s': %d units",
                    material_id, subj_name, len(units),
                )
            except Exception as exc:
                await db.rollback()
                _log.warning("Failed to commit ScheduledTopic records: %s", exc)


async def _create_subject_folders(user_id: int, analyses: list[dict]) -> None:
    """Create on-disk subject folders under uploads/{user_id}/syllabus/{SubjectName}/
    for each identified subject. Each folder will contain a topics.json file
    listing the unit→topic structure for that subject.
    """
    if not analyses:
        return
    try:
        for analysis in analyses:
            subj_name = analysis.get("subject_name", "Unknown")
            subj_code = analysis.get("subject_code", "")
            # Build a filesystem-safe folder name: "SubjectCode_SubjectName" or just name
            if subj_code:
                folder_name = _safe(f"{subj_code}_{subj_name}")
            else:
                folder_name = _safe(subj_name)

            subj_dir = UPLOAD_ROOT / str(user_id) / "syllabus" / folder_name
            subj_dir.mkdir(parents=True, exist_ok=True)

            # Write topics.json with the full unit→topic structure
            import json as _json
            topics_file = subj_dir / "topics.json"
            payload = {
                "subject_name": subj_name,
                "subject_code": subj_code,
                "overview": analysis.get("overview", ""),
                "units": [
                    {
                        "unit_name": u.get("unit_name", ""),
                        "unit_number": u.get("unit_number", 0),
                        "topics": [
                            t.get("name") if isinstance(t, dict) else str(t)
                            for t in u.get("topics", [])
                        ],
                    }
                    for u in analysis.get("units", [])
                ],
            }
            topics_file.write_text(_json.dumps(payload, indent=2, ensure_ascii=False))
            _log.info("Created subject folder: %s (%d units)", subj_dir, len(payload["units"]))
    except Exception as exc:
        _log.warning("Subject folder creation failed: %s", exc)


async def _get_mat_kind(material_id: int) -> str:
    """Return the 'kind' column for a material (tiny helper to avoid circular code)."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(StudyMaterial.kind).where(StudyMaterial.id == material_id)
        )
        row = r.first()
        return row[0] if row else ""


router = APIRouter()
_get_user = get_current_user_dep()

# backend/uploads/{user_id}/{subject}/{kind}/filename
BASE_DIR = Path(__file__).resolve().parents[4]   # → backend/
UPLOAD_ROOT = BASE_DIR / "uploads"

# Accepted file types for study‑material uploads
_ALLOWED_EXTENSIONS = {
    ".pdf", ".pptx", ".ppt", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp",
}

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "Mathematics":      ["math","calculus","algebra","geometry","trigonometry",
                         "statistics","equation","theorem","derivative","integral"],
    "Physics":          ["physics","mechanics","dynamics","thermodynamics","optics",
                         "electricity","magnetism","quantum","relativity","force","energy"],
    "Chemistry":        ["chemistry","organic","inorganic","reaction","molecule","atom",
                         "periodic","bond","acid","base"],
    "Biology":          ["biology","cell","genetics","evolution","ecology","anatomy",
                         "physiology","dna","rna","protein","organism"],
    "Computer Science": ["programming","algorithm","data structure","computer","software",
                         "python","java","database","network","recursion"],
    "History":          ["history","war","civilization","empire","revolution","century",
                         "ancient","medieval","modern"],
    "Literature":       ["literature","novel","poem","author","character","theme",
                         "metaphor","shakespeare","prose"],
    "Economics":        ["economics","market","supply","demand","gdp","inflation",
                         "trade","fiscal","monetary"],
}


def _detect_subject(text: str, filename: str = "") -> str:
    combined = (filename + " " + (text[:500] if text else "")).lower()
    best, best_count = "General", 0
    for subject, kws in _SUBJECT_KEYWORDS.items():
        count = sum(1 for kw in kws if kw in combined)
        if count > best_count:
            best_count, best = count, subject
    return best


def _safe(name: str) -> str:
    return re.sub(r'[^\w.\- ]', '_', name or "upload").strip() or "upload"


# ──────────────────────────────────────────────────────────────────────────────
# Upload
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/upload-schedule")
async def upload_schedule_document(
    file: UploadFile = File(...),
    subject: str = Form(""),
    num_days: int = Form(7),
    hours_per_day: float = Form(2.0),
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    contents = await file.read()
    safe_subj = _safe(subject) if subject.strip() else None

    # Save file immediately
    detected = safe_subj or _detect_subject("", file.filename)
    user_dir = UPLOAD_ROOT / str(current_user.id) / detected / "syllabus"
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / _safe(file.filename)
    dest.write_bytes(contents)

    material = StudyMaterial(
        user_id=current_user.id,
        subject=detected,
        filename=file.filename,
        stored_path=str(dest),
        kind="syllabus",
        topics=[],
        file_size=len(contents),
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    # Extract text + topics + RAG indexing all in background (returns instantly)
    _fire_and_forget(_extract_and_update_bg(
        material_id=material.id, file_path=str(dest),
        subject=detected, filename=file.filename, user_id=current_user.id,
    ))

    return {
        "id": material.id,
        "topicCount": 0,
        "subject": detected,
        "topics": [],
        "numDays": num_days,
        "hoursPerDay": hours_per_day,
        "processing": True,
    }


@router.post("/upload-material")
async def upload_study_material(
    file: UploadFile = File(...),
    subject: str = Form(""),
    unit: str = Form(""),          # optional: which unit/chapter this file covers
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )
    contents = await file.read()
    safe_subj = _safe(subject) if subject.strip() else None

    detected = safe_subj or _detect_subject("", file.filename)
    # Organise files: uploads/{user_id}/{subject}/materials/{unit_name?}/filename
    unit_slug = _safe(unit) if unit.strip() else ""
    if unit_slug:
        user_dir = UPLOAD_ROOT / str(current_user.id) / detected / "materials" / unit_slug
    else:
        user_dir = UPLOAD_ROOT / str(current_user.id) / detected / "materials"
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / _safe(file.filename)
    dest.write_bytes(contents)

    material = StudyMaterial(
        user_id=current_user.id,
        subject=detected,
        unit_name=unit.strip() or None,
        filename=file.filename,
        stored_path=str(dest),
        kind="material",
        topics=[],
        file_size=len(contents),
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    _fire_and_forget(_extract_and_update_bg(
        material_id=material.id, file_path=str(dest),
        subject=detected, filename=file.filename, user_id=current_user.id,
    ))

    return {
        "id": material.id,
        "topicCount": 0,
        "subject": detected,
        "unitName": unit.strip() or None,
        "processing": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# File Management
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/subjects")
async def list_subjects(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """List subjects grouped with unit structure.

    Returns a rich hierarchy:
      subjects: [{name, fileCount, syllabusCount, topicCount, units: [{unitName, fileCount, topicCount}]}]
    """
    result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.user_id == current_user.id)
        .order_by(StudyMaterial.subject, StudyMaterial.unit_name)
    )
    materials = result.scalars().all()

    subjects: dict[str, dict] = {}
    for m in materials:
        subj = m.subject or "General"
        if subj not in subjects:
            subjects[subj] = {
                "name": subj,
                "fileCount": 0,
                "syllabusCount": 0,
                "topicCount": 0,
                "units": {},     # unit_name → {fileCount, topicCount, files:[]}
            }
        s = subjects[subj]
        s["fileCount"] += 1
        if m.kind == "syllabus":
            s["syllabusCount"] += 1
        s["topicCount"] += len(m.topics or [])

        unit_key = m.unit_name or "_default"
        if unit_key not in s["units"]:
            s["units"][unit_key] = {"unitName": m.unit_name, "fileCount": 0, "topicCount": 0, "files": []}
        u = s["units"][unit_key]
        u["fileCount"] += 1
        u["topicCount"] += len(m.topics or [])
        u["files"].append({
            "id": m.id,
            "filename": m.filename,
            "kind": m.kind,
            "topicCount": len(m.topics or []),
        })

    # Flatten units dict → list, sort: syllabi first then materials
    output = []
    for s in subjects.values():
        units_list = sorted(
            s["units"].values(),
            key=lambda u: (u["unitName"] is None, u["unitName"] or ""),
        )
        output.append({
            "name": s["name"],
            "fileCount": s["fileCount"],
            "syllabusCount": s["syllabusCount"],
            "topicCount": s["topicCount"],
            "units": units_list,
        })

    return {"subjects": output}


@router.get("/syllabus-curriculum")
async def get_syllabus_curriculum(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the full parsed curriculum: Subject → Units → Topics.

    This is built exclusively from syllabus files. Study materials are excluded.
    The response mirrors the on-disk folder structure created by the analysis pipeline.

    Response shape:
    {
      "subjects": [
        {
          "subject_name": "Machine Learning",
          "subject_code": "21CS502",
          "overview": "...",
          "syllabus_files": [{"id": 1, "filename": "..."}],
          "units": [
            {
              "unit_name": "Unit I: Introduction",
              "unit_number": 1,
              "topics": [
                {"name": "Supervised Learning", "difficulty": 2, "est_hours": 1.0}
              ]
            }
          ],
          "total_topics": 42
        }
      ]
    }
    """
    analysis_rows = await db.execute(
        select(SubjectAnalysis)
        .where(SubjectAnalysis.user_id == current_user.id)
        .order_by(SubjectAnalysis.subject)
    )
    analyses = analysis_rows.scalars().all()

    # Group by subject name (multiple syllabus files may contribute to same subject)
    by_subject: dict[str, dict] = {}
    for row in analyses:
        subj = row.subject or "Unknown"
        aj = row.analysis_json or {}
        if subj not in by_subject:
            by_subject[subj] = {
                "subject_name": aj.get("subject_name", subj),
                "subject_code": aj.get("subject_code", ""),
                "overview": aj.get("overview", ""),
                "syllabus_files": [],
                "units": aj.get("units", []),
                "total_topics": 0,
            }
        else:
            # Merge units from multiple files for the same subject
            existing_unit_names = {u["unit_name"] for u in by_subject[subj]["units"]}
            for u in aj.get("units", []):
                if u.get("unit_name") not in existing_unit_names:
                    by_subject[subj]["units"].append(u)
                    existing_unit_names.add(u.get("unit_name"))

        # Track which syllabus file this came from
        by_subject[subj]["syllabus_files"].append({
            "materialId": row.material_id,
        })

    # Count total topics per subject
    for subj_data in by_subject.values():
        subj_data["total_topics"] = sum(
            len(u.get("topics", [])) for u in subj_data["units"]
        )

    return {"subjects": list(by_subject.values())}


@router.get("/topic-pages")
async def get_topic_pages(
    topic: str,
    subject: Optional[str] = None,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Find which study material files contain a given topic, and on which page.

    Returns a list of {materialId, filename, subject, kind, page, unitName}
    objects. The frontend can use these to surface "Open PDF — see page N" links
    directly under each schedule task.
    """
    query = select(StudyMaterial).where(
        StudyMaterial.user_id == current_user.id,
        StudyMaterial.topic_pages.isnot(None),
    )
    if subject:
        query = query.where(StudyMaterial.subject == subject)
    result = await db.execute(query)
    materials = result.scalars().all()

    topic_lower = topic.lower().strip()
    matches: list[dict] = []

    for m in materials:
        pages: dict = m.topic_pages or {}
        # Exact match first
        page = pages.get(topic)
        if page is None:
            # Fuzzy: find any stored topic whose text is contained in the query or vice-versa
            for stored_topic, p in pages.items():
                stored_low = stored_topic.lower()
                if topic_lower in stored_low or stored_low in topic_lower:
                    page = p
                    break
        if page is not None:
            matches.append({
                "materialId": m.id,
                "filename": m.filename,
                "subject": m.subject,
                "kind": m.kind,
                "unitName": m.unit_name,
                "page": page,
            })

    return {"topic": topic, "materials": matches}


@router.get("/files")
async def list_files(
    subject: Optional[str] = None,
    unit: Optional[str] = None,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(StudyMaterial).where(StudyMaterial.user_id == current_user.id)
    if subject:
        query = query.where(StudyMaterial.subject == subject)
    if unit:
        query = query.where(StudyMaterial.unit_name == unit)
    query = query.order_by(StudyMaterial.created_at.desc())

    result = await db.execute(query)
    materials = result.scalars().all()

    return {
        "files": [
            {
                "id": m.id,
                "subject": m.subject,
                "unitName": m.unit_name,
                "filename": m.filename,
                "kind": m.kind,
                "topicCount": len(m.topics or []),
                "topics": (m.topics or [])[:100],
                "topicPages": m.topic_pages or {},
                "fileSize": m.file_size,
                "createdAt": m.created_at.isoformat() if m.created_at else None,
                # A file is "processing" if it has no topics yet AND was uploaded
                # less than 10 minutes ago. After 10 min we give up polling —
                # the user can retrigger analysis manually.
                "processing": (
                    len(m.topics or []) == 0
                    and (m.file_size or 0) > 0
                    and (
                        m.created_at is None
                        or (datetime.now(timezone.utc) - m.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 600
                    )
                ),
            }
            for m in materials
        ]
    }


@router.get("/files/{material_id}/topics")
async def get_file_topics(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    mat = result.scalar_one_or_none()
    if not mat:
        raise HTTPException(status_code=404, detail="File not found")
    topics = mat.topics or []
    pending_by_age = (
        len(topics) == 0
        and (mat.file_size or 0) > 0
        and (
            mat.created_at is None
            or (datetime.now(timezone.utc) - mat.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 600
        )
    )

    return {
        "materialId": material_id,
        "topicCount": len(topics),
        "topics": topics,
        "topicPages": mat.topic_pages or {},
        "unitName": mat.unit_name,
        "processing": pending_by_age,
    }


@router.get("/files/{material_id}/analysis")
async def get_file_analysis(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the LLM curriculum analysis for a uploaded syllabus.

    Status:
      - "ready"    — analysis is complete, units / topics / difficulty included
      - "pending"  — file is still being processed (topics not yet extracted)
      - "not_found"— no file or no analysis record yet
    """
    mat_result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    mat = mat_result.scalar_one_or_none()
    if not mat:
        raise HTTPException(status_code=404, detail="File not found")

    analysis_result = await db.execute(
        select(SubjectAnalysis).where(SubjectAnalysis.material_id == material_id)
    )
    record = analysis_result.scalar_one_or_none()

    if record and record.analysis_json:
        return {
            "materialId": material_id,
            "status": "ready",
            "analysis": record.analysis_json,
        }

    # Not yet analyzed — may be pending extraction
    pending = (
        (mat.file_size or 0) > 0
        and len(mat.topics or []) == 0
        and (
            mat.created_at is None
            or (datetime.now(timezone.utc) - mat.created_at.replace(tzinfo=timezone.utc)).total_seconds() < 600
        )
    )
    return {
        "materialId": material_id,
        "status": "pending" if pending else "not_found",
        "analysis": None,
    }


@router.post("/files/{material_id}/analyze")
async def trigger_file_analysis(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-trigger (or first-time trigger) LLM curriculum analysis for an uploaded file.

    Useful for syllabi that were uploaded before the intelligent scheduler existed.
    Analysis runs in the background — poll GET /files/{id}/analysis for the result.
    """
    mat_result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    mat = mat_result.scalar_one_or_none()
    if not mat:
        raise HTTPException(status_code=404, detail="File not found")

    if not mat.stored_path or not Path(mat.stored_path).exists():
        raise HTTPException(status_code=422, detail="Source file no longer on disk")

    async def _analyze_bg():
        import asyncio as _aio
        loop = _aio.get_event_loop()
        try:
            text = await loop.run_in_executor(None, extract_text_from_file, mat.stored_path)
        except Exception as exc:
            _log.warning("Re-analysis text extraction failed for material %s: %s", material_id, exc)
            return
        if not text:
            return
        from app.core.syllabus_intelligence import analyze_syllabus
        analysis = await analyze_syllabus(text, mat.subject or "")
        async with AsyncSessionLocal() as db2:
            existing = await db2.execute(
                select(SubjectAnalysis).where(SubjectAnalysis.material_id == material_id)
            )
            record = existing.scalar_one_or_none()
            if record:
                record.analysis_json = analysis
            else:
                db2.add(SubjectAnalysis(
                    material_id=material_id,
                    user_id=mat.user_id,
                    subject=mat.subject,
                    analysis_json=analysis,
                ))
            await db2.commit()
        _log.info("Re-analysis complete for material %s", material_id)

    _fire_and_forget(_analyze_bg())
    return {"status": "analyzing", "materialId": material_id,
            "message": "Analysis started in background. Poll GET /files/{id}/analysis for result."}


@router.get("/files/{material_id}/topics-hierarchical")
async def get_topics_hierarchical(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Return hierarchical subject → unit → topic structure from ScheduledTopic records.
    
    Response format:
    {
      "subjects": [
        {
          "subject": "Computer Networks",
          "subject_code": "CS301",
          "units": [
            {
              "unit_name": "UNIT-1",
              "unit_index": 0,
              "topics": [
                {
                  "id": 123,
                  "topic_name": "OSI Model",
                  "topic_index": 0,
                  "page_number": 5,
                  "estimated_hours": 1.5,
                  "difficulty": "Medium",
                  "status": "pending",
                  "scheduled_date": null
                },
                ...
              ]
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    # Check file exists and belongs to user
    mat_result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    mat = mat_result.scalar_one_or_none()
    if not mat:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get all ScheduledTopic records for this material, grouped by subject and unit
    topics_result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.material_id == material_id)
        .where(ScheduledTopic.user_id == current_user.id)
        .order_by(
            ScheduledTopic.subject,
            ScheduledTopic.unit_index,
            ScheduledTopic.topic_index,
        )
    )
    scheduled_topics = topics_result.scalars().all()
    
    if not scheduled_topics:
        return {"subjects": []}
    
    # Group by subject → unit
    subjects_dict: dict[str, dict] = {}
    for topic in scheduled_topics:
        if topic.subject not in subjects_dict:
            subjects_dict[topic.subject] = {
                "subject": topic.subject,
                "subject_code": topic.subject_code,
                "units": {},
            }
        
        units = subjects_dict[topic.subject]["units"]
        if topic.unit_name not in units:
            units[topic.unit_name] = {
                "unit_name": topic.unit_name,
                "unit_index": topic.unit_index,
                "topics": [],
            }
        
        units[topic.unit_name]["topics"].append({
            "id": topic.id,
            "topic_name": topic.topic_name,
            "topic_index": topic.topic_index,
            "page_number": topic.page_number,
            "estimated_hours": topic.estimated_hours,
            "difficulty": topic.difficulty,
            "status": topic.status,
            "scheduled_date": topic.scheduled_date.isoformat() if topic.scheduled_date else None,
            "completed_date": topic.completed_date.isoformat() if topic.completed_date else None,
            "rescheduled_date": topic.rescheduled_date.isoformat() if topic.rescheduled_date else None,
        })
    
    # Convert to list and sort units
    subjects = []
    for subj_name in sorted(subjects_dict.keys()):
        subj_data = subjects_dict[subj_name]
        units = sorted(subj_data["units"].values(), key=lambda u: u["unit_index"])
        subj_data["units"] = units
        subjects.append(subj_data)
    
    return {"subjects": subjects}


class CompleteTopicRequest(BaseModel):
    completion_notes: str = ""


class RescheduleTopicRequest(BaseModel):
    new_scheduled_date: str
    reason: str = ""


@router.patch("/scheduled-topics/{topic_id}/complete")
async def mark_topic_complete(
    topic_id: int,
    payload: Optional[CompleteTopicRequest] = None,
    completion_notes: str = "",
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a scheduled topic as completed by the user.
    
    Sets: status="completed", completed_date=(now)
    """
    result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.id == topic_id)
        .where(ScheduledTopic.user_id == current_user.id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    notes = payload.completion_notes if payload is not None else completion_notes

    topic.status = "completed"
    topic.completed_date = datetime.now(timezone.utc)
    if notes:
        topic.completion_notes = notes
    
    await db.commit()
    return {
        "id": topic.id,
        "status": topic.status,
        "completed_date": topic.completed_date.isoformat(),
        "message": "Topic marked as complete",
    }


@router.patch("/scheduled-topics/{topic_id}/reschedule")
async def reschedule_topic(
    topic_id: int,
    payload: Optional[RescheduleTopicRequest] = None,
    new_scheduled_date: str = "",  # query fallback for compatibility
    reason: str = "",
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Reschedule a topic to a new date.
    
    Sets: scheduled_date=(new_date), status="rescheduled", rescheduled_date=(now)
    """
    result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.id == topic_id)
        .where(ScheduledTopic.user_id == current_user.id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    final_date = payload.new_scheduled_date if payload is not None else new_scheduled_date
    final_reason = payload.reason if payload is not None else reason

    try:
        new_date = datetime.fromisoformat(final_date.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use ISO 8601.")
    
    topic.scheduled_date = new_date
    topic.status = "rescheduled"
    topic.rescheduled_date = datetime.now(timezone.utc)
    if final_reason:
        topic.completion_notes = f"Rescheduled: {final_reason}"
    
    await db.commit()
    return {
        "id": topic.id,
        "status": topic.status,
        "scheduled_date": topic.scheduled_date.isoformat(),
        "rescheduled_date": topic.rescheduled_date.isoformat(),
        "message": "Topic rescheduled",
    }


@router.get("/scheduled-topics")
async def query_scheduled_topics(
    material_id: int = None,
    subject: str = None,
    status: str = None,  # "pending", "completed", "rescheduled", "skipped"
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Query ScheduledTopic records with optional filters.
    
    Useful for schedulers to fetch available topics by status/subject.
    """
    query = select(ScheduledTopic).where(ScheduledTopic.user_id == current_user.id)
    
    if material_id:
        query = query.where(ScheduledTopic.material_id == material_id)
    if subject:
        query = query.where(ScheduledTopic.subject == subject)
    if status:
        query = query.where(ScheduledTopic.status == status)
    
    result = await db.execute(query.order_by(ScheduledTopic.created_at))
    topics = result.scalars().all()
    
    return {
        "count": len(topics),
        "topics": [
            {
                "id": t.id,
                "subject": t.subject,
                "unit_name": t.unit_name,
                "topic_name": t.topic_name,
                "estimated_hours": t.estimated_hours,
                "status": t.status,
                "scheduled_date": t.scheduled_date.isoformat() if t.scheduled_date else None,
                "page_number": t.page_number,
            }
            for t in topics
        ],
    }


@router.get("/files/{material_id}/download")
async def download_file(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the original uploaded file back to the browser."""
    import mimetypes as _mt

    result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    mat = result.scalar_one_or_none()
    if not mat:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(mat.stored_path) if mat.stored_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="File no longer on disk")

    # Serve with correct MIME so the browser can open PDFs / PPTs inline
    mime = _mt.guess_type(mat.filename)[0] or "application/octet-stream"
    return FileResponse(
        path=str(path),
        filename=mat.filename,
        media_type=mime,
        content_disposition_type="inline",
    )


@router.delete("/files/{material_id}")
async def delete_file(
    material_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyMaterial)
        .where(StudyMaterial.id == material_id)
        .where(StudyMaterial.user_id == current_user.id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="File not found")
    material_id = material.id
    try:
        Path(material.stored_path).unlink(missing_ok=True)
    except Exception:
        pass
    await db.delete(material)
    await db.commit()
    # Remove chunks from RAG index
    await rag.delete_chunks(material_id=material_id, db=db)
    return {"status": "deleted"}


# ──────────────────────────────────────────────────────────────────────────────
# AI Study Chatbot  (RAG-powered via Ollama)
# ──────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    subject: Optional[str] = None


@router.get("/topic-resources")
async def get_topic_resources(
    topic: str,
    subject: str = "",
    limit: int = 6,
    current_user: User = Depends(_get_user),
):
    """Generate study resources (web search + YouTube) for a topic.
    
    Returns:
        resources: List of resource links with title, url, and type
    """
    if not topic or len(topic.strip()) < 2:
        raise HTTPException(status_code=400, detail="Topic must be at least 2 characters")
    
    # Sanitize topic name for URL encoding
    clean_topic = topic.strip()
    if subject:
        clean_subject = subject.strip()
        search_query = f"{clean_topic} {clean_subject}"
    else:
        search_query = clean_topic
    
    # URL encode for search queries
    from urllib.parse import quote
    encoded = quote(search_query)
    
    # Generate two key resources: web search and YouTube
    resources = [
        {
            "title": f"Web Search: {clean_topic}",
            "url": f"https://www.google.com/search?q={encoded}",
            "type": "web",
            "icon": "🔍"
        },
        {
            "title": f"YouTube Videos: {clean_topic}",
            "url": f"https://www.youtube.com/results?search_query={encoded}",
            "type": "video",
            "icon": "▶️"
        }
    ]
    
    return { "resources": resources[:limit] }


@router.post("/chat")
async def chat_with_study_bot(
    body: ChatRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG-powered Q&A: embeds the question, retrieves top-K chunks from the
    user's uploaded documents, then generates an answer with Ollama llama3.2:1b.
    Falls back to formatted context snippets when Ollama is unavailable."""
    return await rag.answer(
        user_id=current_user.id,
        question=body.question,
        db=db,
    )


@router.get("/rag-status")
async def rag_status():
    """Returns which Ollama models are available (useful for UI status badge)."""
    return await rag.ollama_status()


@router.post("/chat-stream")
async def stream_chat(
    body: ChatRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint: streams Ollama tokens one-by-one to the frontend.

    Each event is ``data: {"token": "..."}\\n\\n``.
    A final ``data: [DONE]\\n\\n`` signals the end of the stream.
    Falls back to a single chunk when Ollama is unavailable.
    """
    async def _generate():
        try:
            async for token in rag.answer_stream(
                user_id=current_user.id,
                question=body.question,
                db=db,
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'Error: {exc}'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


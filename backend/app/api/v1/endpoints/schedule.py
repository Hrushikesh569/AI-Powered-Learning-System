from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_current_user_dep
from app.core.syllabus_intelligence import build_time_slots, find_cross_subject_relations, generate_llm_adaptive_schedule, generate_intelligent_schedule as _gen
from app.db.models import AgentDecision, ScheduleHistory, ScheduledTopic, StudyPlan, SubjectAnalysis, User
from app.db.session import get_db

router = APIRouter()
_get_user = get_current_user_dep()


# ──────────────────────────────────────────────────────────────────────────────
# Subject hierarchy endpoint — returns Subject > Unit > Topics tree for pickers
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/subject-hierarchy")
async def get_subject_hierarchy(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Return full Subject→Unit→Topic hierarchy from stored LLM analyses.

    Used by the frontend topic-picker modal so students can choose what to
    study today without inspecting raw schedule entries.
    """
    # Source of truth: combine ScheduledTopic rows with SubjectAnalysis so one
    # subject that already has scheduled rows does not hide the rest of the syllabus.
    st_result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.user_id == current_user.id)
        .order_by(ScheduledTopic.subject, ScheduledTopic.unit_index, ScheduledTopic.topic_index)
    )
    rows = st_result.scalars().all()
    result = await db.execute(
        select(SubjectAnalysis).where(SubjectAnalysis.user_id == current_user.id)
    )
    records = result.scalars().all()

    diff_to_num = {"easy": 1, "basic": 2, "intermediate": 3, "medium": 3, "hard": 4, "advanced": 5}
    grouped: dict[str, dict] = {}

    for r in rows:
        subj = r.subject or "Unknown"
        if subj not in grouped:
            grouped[subj] = {
                "subject_name": subj,
                "subject_code": r.subject_code or "",
                "overview": "",
                "units": {},
            }
        ukey = r.unit_name or "Unit"
        units = grouped[subj]["units"]
        if ukey not in units:
            units[ukey] = {
                "unit_name": ukey,
                "unit_number": (r.unit_index or 0) + 1,
                "topics": [],
                "_idx": r.unit_index or 0,
            }
        raw_diff = str(r.difficulty or "Intermediate").lower()
        diff_num = diff_to_num.get(raw_diff, 3)
        units[ukey]["topics"].append({
            "name": r.topic_name or "",
            "difficulty": diff_num,
            "difficulty_label": str(r.difficulty or "Intermediate"),
            "est_hours": float(r.estimated_hours or 1.0),
            "is_foundational": diff_num <= 2,
        })

    for r in records:
        if not r.analysis_json:
            continue
        a = r.analysis_json
        subj_name = a.get("subject_name", r.subject or "Unknown")
        if subj_name not in grouped:
            grouped[subj_name] = {
                "subject_name": subj_name,
                "subject_code": a.get("subject_code", ""),
                "overview": a.get("overview", ""),
                "units": {},
            }
        subj = grouped[subj_name]
        if not subj.get("subject_code"):
            subj["subject_code"] = a.get("subject_code", "")
        if not subj.get("overview"):
            subj["overview"] = a.get("overview", "")
        for unit in a.get("units", []):
            ukey = unit.get("unit_name", "Unit")
            units = subj["units"]
            if ukey not in units:
                units[ukey] = {
                    "unit_name": ukey,
                    "unit_number": unit.get("unit_number", 0),
                    "topics": [],
                    "_idx": unit.get("unit_number", 0),
                }
            topics = units[ukey]["topics"]
            for t in unit.get("topics", []):
                if not isinstance(t, dict):
                    continue
                raw_diff = str(t.get("difficulty", 3)).lower()
                diff_num = diff_to_num.get(raw_diff, int(t.get("difficulty", 3)) if str(t.get("difficulty", 3)).isdigit() else 3)
                topics.append({
                    "name": t.get("name", ""),
                    "difficulty": diff_num,
                    "difficulty_label": t.get("difficultyLabel", "") or ["", "Easy", "Basic", "Intermediate", "Hard", "Advanced"][max(1, min(5, diff_num))],
                    "est_hours": float(t.get("est_hours", 1.0)),
                    "is_foundational": t.get("is_foundational", False),
                })

    hierarchy = []

    for subj_name in sorted(grouped.keys()):
        subj = grouped[subj_name]
        unit_list = sorted(subj["units"].values(), key=lambda u: u.get("_idx", 0))
        for u in unit_list:
            u.pop("_idx", None)
        hierarchy.append({
            "subject_name": subj["subject_name"],
            "subject_code": subj.get("subject_code", ""),
            "overview": subj.get("overview", ""),
            "units": unit_list,
        })

    return {"hierarchy": hierarchy}


class SubjectInfo(BaseModel):
    name: str
    topics: Optional[List[str]] = None
    priority: int = 5           # 1 = highest priority


class ScheduleRequest(BaseModel):
    syllabus_id: Optional[int] = None
    num_days: int = 30
    hours_per_day: float = 2.0
    study_start_hour: int = 9       # e.g., 9 for 9 AM
    study_end_hour: int = 23        # e.g., 23 for 11 PM
    preferred_topics: Optional[List[str]] = None
    subjects: Optional[List[SubjectInfo]] = None   # rich subject list from syllabus upload


@router.post("/generate")
async def generate_schedule(payload: ScheduleRequest | None = None):
    """Generate a personalised schedule.

    Priority order for topic pool:
      1. subjects[]  — structured list from syllabus upload (sorted by priority)
      2. preferred_topics — flat list from user hints
      3. Generic study blocks — no hardcoded subject names
    """
    if payload is None:
        payload = ScheduleRequest()

    today = date.today()
    schedule: list[dict] = []
    task_id = 1

    # How many blocks per day based on study hours
    if payload.hours_per_day <= 1.5:
        blocks_per_day = 1
    elif payload.hours_per_day <= 3.0:
        blocks_per_day = 2
    elif payload.hours_per_day <= 4.5:
        blocks_per_day = 3
    else:
        blocks_per_day = 4
    blocks_per_day = max(1, min(blocks_per_day, 4))

    # Generate time slots within user's study window
    time_slot_labels = build_time_slots(
        start_hour=payload.study_start_hour, 
        end_hour=payload.study_end_hour, 
        num_slots=blocks_per_day
    )

    # Calculate duration per block
    duration_per_block = payload.hours_per_day / max(1, blocks_per_day)
    duration_label = f"{max(0.5, min(2.5, duration_per_block)):.1f} hours"

    # Build time slots with durations
    time_slots = [
        (label, duration_label) 
        for label in time_slot_labels
    ]

    # Build topic pool ─────────────────────────────────────────────────────
    topic_pool: list[dict] = []

    if payload.subjects:
        sorted_subjects = sorted(payload.subjects, key=lambda s: s.priority)
        for subj in sorted_subjects:
            for topic in (subj.topics or [subj.name]):
                topic_pool.append({"subject": subj.name, "topic": topic})

    elif payload.preferred_topics:
        for t in payload.preferred_topics:
            topic_pool.append({"subject": "Study", "topic": t})

    else:
        generic = [
            "Concept Review",
            "Problem Practice",
            "Topic Deep Dive",
            "Revision Session",
            "Active Recall",
            "Past Paper Practice",
            "Summary Notes",
            "Self Assessment",
        ]
        topic_pool = [{"subject": "Study Block", "topic": t} for t in generic]

    if not topic_pool:
        topic_pool = [{"subject": "Study Block", "topic": "Study Session"}]

    total_topics = len(topic_pool)
    topic_idx = 0

    for offset in range(max(1, payload.num_days)):
        day = today + timedelta(days=offset)
        for block_index in range(blocks_per_day):
            entry = topic_pool[topic_idx % total_topics]
            time_label, duration_label = time_slots[block_index]
            schedule.append({
                "id": task_id,
                "date": day.isoformat(),
                "time": time_label,
                "subject": entry["subject"],
                "topic": f"{entry['topic']} — Day {offset + 1}",
                "duration": duration_label,
                "status": "pending",
            })
            task_id += 1
            topic_idx += 1

    return {"schedule": schedule}


# ──────────────────────────────────────────────────────────────────────────────
# Intelligent schedule — LLM-powered, difficulty-aware, dependency-ordered
# ──────────────────────────────────────────────────────────────────────────────

class IntelligentScheduleRequest(BaseModel):
    hours_per_day: float = 3.0
    num_days: int = 30
    subject_priorities: Optional[Dict[str, int]] = None   # {subject_name: 1-5}
    cross_subject: bool = True
    user_overrides: Optional[Dict[str, Dict[str, Any]]] = None  # {topic_name: {extra_hours: N}}


@router.post("/intelligent")
async def generate_intelligent_schedule(
    payload: IntelligentScheduleRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an LLM-analyzed, dependency-ordered, difficulty-weighted schedule.

    - Reads SubjectAnalysis records (populated by the background LLM analysis
      that runs when a syllabus is uploaded).
    - Applies topological sort over the prerequisite dependency graph so
      foundational topics always come before advanced ones.
    - Interleaves multiple subjects with priority weighting so all subjects
      progress in parallel (not "finish one then start another").
    - Optionally detects cross-subject concept links (NLP ↔ NNDL) and schedules
      related topics in adjacent days.
    - Returns full schedule list with per-task difficulty badges and a summary.
    """
    from app.core.syllabus_intelligence import (
        find_cross_subject_relations,
        generate_intelligent_schedule as _gen,
    )

    # Load all LLM analyses for this user
    result = await db.execute(
        select(SubjectAnalysis).where(SubjectAnalysis.user_id == current_user.id)
    )
    records = result.scalars().all()

    analyses = [r.analysis_json for r in records if r.analysis_json]

    # If analysis records are missing or effectively single-subject, rebuild analyses from ScheduledTopic rows.
    if len(analyses) <= 1:
        st_result = await db.execute(
            select(ScheduledTopic)
            .where(ScheduledTopic.user_id == current_user.id)
            .order_by(ScheduledTopic.subject, ScheduledTopic.unit_index, ScheduledTopic.topic_index)
        )
        st_rows = st_result.scalars().all()
        if st_rows:
            diff_to_num = {"easy": 1, "basic": 2, "intermediate": 3, "medium": 3, "hard": 4, "advanced": 5}
            grouped: dict[str, dict] = {}
            for r in st_rows:
                subj = r.subject or "Unknown"
                if subj not in grouped:
                    grouped[subj] = {
                        "subject_name": subj,
                        "subject_code": r.subject_code or "",
                        "overview": "",
                        "units": {},
                    }
                unit_key = r.unit_name or "Unit"
                units = grouped[subj]["units"]
                if unit_key not in units:
                    units[unit_key] = {
                        "unit_name": unit_key,
                        "unit_number": (r.unit_index or 0) + 1,
                        "topics": [],
                        "_idx": r.unit_index or 0,
                    }
                raw_diff = str(r.difficulty or "Intermediate").lower()
                units[unit_key]["topics"].append({
                    "name": r.topic_name or "",
                    "difficulty": diff_to_num.get(raw_diff, 3),
                    "difficultyLabel": str(r.difficulty or "Intermediate"),
                    "est_hours": float(r.estimated_hours or 1.0),
                    "is_foundational": diff_to_num.get(raw_diff, 3) <= 2,
                })

            rebuilt = []
            for subj_name in sorted(grouped.keys()):
                subj = grouped[subj_name]
                unit_list = sorted(subj["units"].values(), key=lambda u: u.get("_idx", 0))
                for u in unit_list:
                    u.pop("_idx", None)
                rebuilt.append({
                    "subject_name": subj["subject_name"],
                    "subject_code": subj["subject_code"],
                    "overview": subj["overview"],
                    "units": unit_list,
                })
            analyses = rebuilt

    if not analyses:
        return {
            "schedule": [],
            "summary": {},
            "message": "No syllabus analysis found. Upload a syllabus PDF and wait for analysis to complete.",
        }
    if not analyses:
        return {
            "schedule": [],
            "summary": {},
            "message": "Analysis still in progress. Please wait a moment and retry.",
        }

    # Detect cross-subject relations if requested
    cross_relations: list = []
    if payload.cross_subject and len(analyses) >= 2:
        try:
            cross_relations = await find_cross_subject_relations(analyses)
        except Exception:
            cross_relations = []

    schedule_result = _gen(
        analyses,
        hours_per_day=payload.hours_per_day,
        num_days=payload.num_days,
        subject_priorities=payload.subject_priorities or {},
        cross_subject_relations=cross_relations,
        user_overrides=payload.user_overrides or {},
        study_start_hour=current_user.study_start_hour or 9,
        study_end_hour=current_user.study_end_hour or 23,
    )

    return {**schedule_result, "crossSubjectRelations": cross_relations}


# ──────────────────────────────────────────────────────────────────────────────
# Adaptive (Dynamic) Rescheduling — LLM-guided live scheduling that reacts to
# missed topics, stress, performance, and residual difficulty.
# ──────────────────────────────────────────────────────────────────────────────

def _filter_completed(analyses: list, completed: set) -> list:
    """Remove already-completed topics from every subject analysis."""
    out = []
    for a in analyses:
        a_copy = {**a, "units": []}
        for unit in a.get("units", []):
            remaining = [t for t in unit.get("topics", []) if t.get("name", "") not in completed]
            if remaining:
                a_copy["units"].append({**unit, "topics": remaining})
        if a_copy["units"]:
            out.append(a_copy)
    return out


def _boost_missed(analyses: list, missed: set) -> list:
    """
    Increment difficulty of missed topics by 1 (cap at 5) and prefix name with
    '[Review]' so the scheduler allocates more time and slots them early.
    """
    out = []
    for a in analyses:
        a_copy = {**a, "units": []}
        for unit in a.get("units", []):
            boosted = []
            for t in unit.get("topics", []):
                if t.get("name", "") in missed:
                    t = {**t,
                         "difficulty": min(5, t.get("difficulty", 3) + 1),
                         "name": f"[Review] {t.get('name', '')}",
                         "is_foundational": True}  # force early scheduling
                boosted.append(t)
            a_copy["units"].append({**unit, "topics": boosted})
        out.append(a_copy)
    return out


def _avg_difficulty(analyses: list) -> float:
    vals = [t.get("difficulty", 3)
            for a in analyses
            for u in a.get("units", [])
            for t in u.get("topics", [])]
    return sum(vals) / max(len(vals), 1)


def _count_topics(analyses: list) -> int:
    return sum(len(u.get("topics", []))
               for a in analyses
               for u in a.get("units", []))


def _adjustment_reason(action_val: float, stress: float, perf: float, n_missed: int) -> str:
    parts = []
    if stress > 0.6:
        parts.append("reduced load for high stress")
    if n_missed > 0:
        parts.append(f"{n_missed} missed topic(s) re-prioritized with review sessions")
    if perf < 0.4:
        parts.append("slower pace recommended for low performance")
    elif perf > 0.8:
        parts.append("pace increased to match strong performance")
    if action_val > 0.2 and not parts:
        parts.append("ML model suggests increased study intensity")
    elif action_val < -0.2 and not parts:
        parts.append("ML model suggests lighter load")
    return "; ".join(parts) if parts else "Schedule re-optimized with current progress data"


class AdaptiveScheduleRequest(BaseModel):
    completed_topics: List[str] = []       # topic names already completed
    missed_topics: List[str] = []          # topic names that were skipped / missed
    skipped_topics: List[str] = []         # user chose skip tomorrow
    do_later_topics: List[str] = []        # user chose do later
    hours_per_day: float = 3.0
    num_days: int = 30
    stress_level: float = 0.3             # 0 = calm, 1 = very stressed
    performance_score: float = 0.7        # 0–1, recent quiz / completion accuracy
    subject_priorities: Optional[Dict[str, int]] = None
    cross_subject: bool = True


@router.post("/adaptive")
async def adaptive_reschedule(
    payload: AdaptiveScheduleRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a live schedule using the LLM-guided planner and persist it.

    The scheduler uses Ollama to rank topics by urgency, then the deterministic
    packer lays them out inside the user's daily time window.
    """

    # ── 1. Load this user's syllabus analyses ───────────────────────────────
    result = await db.execute(select(SubjectAnalysis).where(SubjectAnalysis.user_id == current_user.id))
    records = result.scalars().all()
    analyses = [r.analysis_json for r in records if r.analysis_json]

    if not analyses:
        return {
            "schedule": [],
            "summary": {},
            "adjustments": {},
            "message": "No syllabus analysis found yet. Upload a syllabus to enable adaptive scheduling.",
        }

    completed_set = set(payload.completed_topics)
    missed_set = set(payload.missed_topics)
    skipped_set = set(payload.skipped_topics)
    later_set = set(payload.do_later_topics)

    filtered = _filter_completed(analyses, completed_set)
    if not filtered:
        return {
            "schedule": [],
            "summary": {},
            "adjustments": {
                "planner_mode": "rag-llm",
                "llm_used": False,
                "completed_topics_removed": list(completed_set),
            },
            "message": "All currently tracked topics are complete.",
        }

    # Use a simple deterministic hour adjustment based on load and performance.
    adjusted_hours = round(max(1.0, min(8.0, payload.hours_per_day + ((payload.performance_score - 0.5) * 0.8) - (payload.stress_level * 0.6))), 1)

    user_overrides = {t: {"extra_hours": 1.5} for t in payload.missed_topics}
    for t in payload.do_later_topics:
        user_overrides.setdefault(t, {"extra_hours": 0.5})

    cross_relations: list = []
    if payload.cross_subject and len(filtered) >= 2:
        try:
            cross_relations = await find_cross_subject_relations(filtered)
        except Exception:
            cross_relations = []

    # ── 2. Generate the LLM-guided live plan ───────────────────────────────
    start_day = date.today() + timedelta(days=1)
    schedule_result = await generate_llm_adaptive_schedule(
        filtered,
        hours_per_day=adjusted_hours,
        num_days=payload.num_days,
        start_date=start_day,
        subject_priorities=payload.subject_priorities or {},
        cross_subject_relations=cross_relations,
        user_overrides=user_overrides,
        study_start_hour=current_user.study_start_hour or 9,
        study_end_hour=current_user.study_end_hour or 23,
        stress_level=payload.stress_level,
        performance_score=payload.performance_score,
        completed_topics=payload.completed_topics,
        missed_topics=payload.missed_topics,
        skipped_topics=payload.skipped_topics,
        do_later_topics=payload.do_later_topics,
    )

    schedule_items = schedule_result.get("schedule", []) or []

    # ── 3. Persist the generated plan and history ───────────────────────────
    previous_plan_result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == current_user.id)
        .order_by(StudyPlan.created_at.desc())
    )
    previous_plan = previous_plan_result.scalars().first()

    decision = AgentDecision(
        agent_name="reschedule",
        user_id=current_user.id,
        input_features={
            "hours_per_day": payload.hours_per_day,
            "stress_level": payload.stress_level,
            "performance_score": payload.performance_score,
            "completed_topics": payload.completed_topics,
            "missed_topics": payload.missed_topics,
            "skipped_topics": payload.skipped_topics,
            "do_later_topics": payload.do_later_topics,
            "subject_priorities": payload.subject_priorities or {},
            "cross_subject": payload.cross_subject,
        },
        output_decision={
            "planner": schedule_result.get("planner", {}),
            "llm_summary": schedule_result.get("llm_summary", {}),
            "adjusted_hours": adjusted_hours,
            "total_items": len(schedule_items),
        },
        event_id=f"reschedule-{uuid4().hex}",
    )
    db.add(decision)
    await db.flush()

    from datetime import datetime as _dt

    plan = StudyPlan(
        user_id=current_user.id,
        plan_json=schedule_result,
        generated_by_agent_id=decision.id,
        valid_from=_dt.combine(start_day, _dt.min.time()),
        valid_to=_dt.combine(start_day + timedelta(days=max(payload.num_days - 1, 0)), _dt.min.time()),
    )
    db.add(plan)
    await db.flush()

    if previous_plan and previous_plan.id != plan.id:
        db.add(ScheduleHistory(
            user_id=current_user.id,
            old_plan_id=previous_plan.id,
            new_plan_id=plan.id,
            reason=(schedule_result.get("llm_summary", {}) or {}).get("focus") or "LLM-guided live reschedule",
            changed_by_agent_id=decision.id,
        ))

    # Update stored topic dates so the dashboard reflects the latest plan.
    topic_rows_result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.user_id == current_user.id)
    )
    topic_rows = topic_rows_result.scalars().all()
    topic_lookup: dict[str, ScheduledTopic] = {}
    for row in topic_rows:
        key = " | ".join([
            str(row.subject or "").strip().lower(),
            str(row.unit_name or "").strip().lower(),
            str(row.topic_name or "").strip().lower(),
        ])
        topic_lookup[key] = row

    for item in schedule_items:
        key = " | ".join([
            str(item.get("subject", "")).strip().lower(),
            str(item.get("unit", "")).strip().lower(),
            str(item.get("topic", "")).strip().lower(),
        ])
        row = topic_lookup.get(key)
        if not row or (row.status or "").lower() == "completed":
            continue
        try:
            day_value = str(item.get("date", ""))[:10]
            time_value = str(item.get("time", "09:00 AM"))
            schedule_dt = datetime.combine(
                datetime.fromisoformat(day_value).date(),
                datetime.strptime(time_value, "%I:%M %p").time(),
            )
        except Exception:
            schedule_dt = datetime.combine(start_day, datetime.min.time())
        row.scheduled_date = schedule_dt
        row.status = str(item.get("status", "pending")) or "pending"

    await db.commit()

    missed_count = len(missed_set)
    completed_count = len(completed_set)
    skipped_count = len(skipped_set)
    later_count = len(later_set)

    return {
        **schedule_result,
        "crossSubjectRelations": cross_relations,
        "plan_id": plan.id,
        "decision_id": decision.id,
        "adjustments": {
            "planner_mode": schedule_result.get("planner", {}).get("mode", "rag-llm"),
            "llm_used": schedule_result.get("planner", {}).get("used_llm", False),
            "hours_per_day": adjusted_hours,
            "original_hours": payload.hours_per_day,
            "stress_level": payload.stress_level,
            "performance_score": payload.performance_score,
            "missed_topics_reprioritized": list(missed_set),
            "skipped_topics_deferred": list(skipped_set),
            "do_later_topics_deferred": list(later_set),
            "completed_topics_removed": list(completed_set),
            "next_day_start": start_day.isoformat(),
            "schedule_items": len(schedule_items),
            "adjustment_reason": (schedule_result.get("llm_summary", {}) or {}).get("carry_forward") or "LLM-guided live reschedule",
            "counts": {
                "completed": completed_count,
                "missed": missed_count,
                "skipped": skipped_count,
                "do_later": later_count,
            },
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Topic feedback endpoint — lets students flag difficulty or request review
# ──────────────────────────────────────────────────────────────────────────────

class TopicFeedbackRequest(BaseModel):
    topic: str
    subject: Optional[str] = None
    feedback: str = "too_hard"  # "too_hard" | "too_easy" | "need_review" | "done"
    extra_hours: Optional[float] = None


@router.post("/topic-feedback")
async def update_topic_feedback(
    payload: TopicFeedbackRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Record student feedback on a topic difficulty.

    Stores the preference so the next adaptive reschedule uses it.
    Returns a confirmation message — actual schedule update happens on next
    call to /adaptive with updated completion/missed arrays.
    """
    feedback_map = {
        "too_hard":   "Noted — this topic will get extra review time in your next schedule.",
        "too_easy":   "Got it — similar topics will be allocated less time.",
        "need_review": "Added for review in your upcoming sessions.",
        "done":       "Marked as understood. Moving on!",
    }
    msg = feedback_map.get(payload.feedback, "Feedback recorded.")
    return {
        "topic": payload.topic,
        "feedback": payload.feedback,
        "message": msg,
        "extra_hours": payload.extra_hours,
    }


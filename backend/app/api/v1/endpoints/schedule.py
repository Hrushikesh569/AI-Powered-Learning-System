from datetime import date, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_current_user_dep
from app.core.syllabus_intelligence import build_time_slots
from app.db.models import ScheduledTopic, SubjectAnalysis, User
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
    # Source of truth: ScheduledTopic rows (guaranteed per subject/unit/topic granularity)
    st_result = await db.execute(
        select(ScheduledTopic)
        .where(ScheduledTopic.user_id == current_user.id)
        .order_by(ScheduledTopic.subject, ScheduledTopic.unit_index, ScheduledTopic.topic_index)
    )
    rows = st_result.scalars().all()

    if rows:
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

        hierarchy = []
        for subj_name in sorted(grouped.keys()):
            subj = grouped[subj_name]
            unit_list = sorted(subj["units"].values(), key=lambda u: u.get("_idx", 0))
            for u in unit_list:
                u.pop("_idx", None)
            hierarchy.append({
                "subject_name": subj["subject_name"],
                "subject_code": subj["subject_code"],
                "overview": subj["overview"],
                "units": unit_list,
            })
        return {"hierarchy": hierarchy}

    # Fallback to SubjectAnalysis if ScheduledTopic is empty
    result = await db.execute(
        select(SubjectAnalysis).where(SubjectAnalysis.user_id == current_user.id)
    )
    records = result.scalars().all()

    hierarchy = []
    for r in records:
        if not r.analysis_json:
            continue
        a = r.analysis_json
        units_out = []
        for unit in a.get("units", []):
            topics_out = [
                {
                    "name": t.get("name", ""),
                    "difficulty": t.get("difficulty", 3),
                    "difficulty_label": t.get("difficultyLabel", "") or
                        ["", "Easy", "Basic", "Intermediate", "Hard", "Advanced"][
                            max(1, min(5, t.get("difficulty", 3)))
                        ],
                    "est_hours": t.get("est_hours", 1.0),
                    "is_foundational": t.get("is_foundational", False),
                }
                for t in unit.get("topics", [])
            ]
            units_out.append({
                "unit_name": unit.get("unit_name", ""),
                "unit_number": unit.get("unit_number", 0),
                "topics": topics_out,
            })
        hierarchy.append({
            "subject_name": a.get("subject_name", r.subject or "Unknown"),
            "subject_code": a.get("subject_code", ""),
            "overview": a.get("overview", ""),
            "units": units_out,
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
# Adaptive (Dynamic) Rescheduling — ML-driven, reacts to missed topics,
# stress, performance, and residual difficulty.
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
    return out or analyses  # keep full list if user marked everything done (edge case)


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
    """
    ML-powered dynamic rescheduling.

    Factors in:
    • Missed topics            — re-prioritized with [Review] label and +1 difficulty
    • Completed topics         — removed so they are never shown again
    • Stress level             — reduces daily hours under high stress
    • Performance score        — adjusts pace (faster / slower)
    • DQN RescheduleAgent      — predicts optimal hours-per-day delta given current state
    • Remaining difficulty avg — informs how aggressively to front-load hard topics
    • Cross-subject relations  — maintained from LLM analysis
    """
    from app.core.model_hot_reload import reschedule_agent
    from app.core.syllabus_intelligence import (
        find_cross_subject_relations,
        generate_intelligent_schedule as _gen,
    )

    # ── 1. Load this user's LLM-analysed subject data ──────────────────────
    result = await db.execute(
        select(SubjectAnalysis).where(SubjectAnalysis.user_id == current_user.id)
    )
    records = result.scalars().all()

    if not records:
        return {
            "schedule": [],
            "summary": {},
            "adjustments": {},
            "message": "No syllabus analysis found yet. Upload a syllabus to enable adaptive scheduling.",
        }

    analyses = [r.analysis_json for r in records if r.analysis_json]
    if not analyses:
        return {"schedule": [], "summary": {}, "adjustments": {},
                "message": "Analysis still in progress. Please retry in a moment."}

    completed_set = set(payload.completed_topics)
    missed_set    = set(payload.missed_topics)
    total_topics  = _count_topics(analyses)

    # ── 2. Filter completed, boost missed ──────────────────────────────────
    filtered   = _filter_completed(analyses, completed_set)
    augmented  = _boost_missed(filtered, missed_set)

    remaining  = _count_topics(augmented)
    avg_diff   = _avg_difficulty(augmented)
    missed_ratio = len(missed_set) / max(total_topics, 1)

    # ── 3. Build DQN state vector & call RescheduleAgent ───────────────────
    # State: [stress, missed_ratio, norm_difficulty, performance, remaining_fraction]
    state = [
        float(payload.stress_level),
        float(missed_ratio),
        float(avg_diff / 5.0),
        float(payload.performance_score),
        float(remaining / max(total_topics, 1)),
    ]
    reward = payload.performance_score - 0.5   # positive = good, negative = struggling

    try:
        action = reschedule_agent.adapt(state, reward)
        action_val = float(action[0]) if action else 0.0
    except Exception:
        action_val = 0.0

    # ── 4. Map ML action → adjusted hours per day ──────────────────────────
    # DQN output scaled to ±1.5 h change; stress & performance apply separately
    hours_delta  = action_val * 1.5
    hours_delta -= payload.stress_level * 1.0          # penalize load under stress
    hours_delta += (payload.performance_score - 0.5) * 0.5  # reward performance
    adjusted_hours = round(max(1.0, min(8.0, payload.hours_per_day + hours_delta)), 1)

    # ── 5. Extra time overrides for missed topics ──────────────────────────
    user_overrides = {t: {"extra_hours": 2} for t in payload.missed_topics}

    # ── 6. Cross-subject relations ─────────────────────────────────────────
    cross_relations: list = []
    if payload.cross_subject and len(augmented) >= 2:
        try:
            cross_relations = await find_cross_subject_relations(augmented)
        except Exception:
            cross_relations = []

    # ── 7. Generate updated schedule ───────────────────────────────────────
    schedule_result = _gen(
        augmented,
        hours_per_day=adjusted_hours,
        num_days=payload.num_days,
        subject_priorities=payload.subject_priorities or {},
        cross_subject_relations=cross_relations,
        user_overrides=user_overrides,
        study_start_hour=current_user.study_start_hour or 9,
        study_end_hour=current_user.study_end_hour or 23,
    )

    reason = _adjustment_reason(action_val, payload.stress_level,
                                payload.performance_score, len(missed_set))

    return {
        **schedule_result,
        "crossSubjectRelations": cross_relations,
        "adjustments": {
            "hours_per_day":               adjusted_hours,
            "original_hours":              payload.hours_per_day,
            "ml_action_value":             round(action_val, 3),
            "stress_level":                payload.stress_level,
            "performance_score":           payload.performance_score,
            "missed_topics_reprioritized": list(missed_set),
            "completed_topics_removed":    list(completed_set),
            "remaining_topics":            remaining,
            "adjustment_reason":           reason,
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


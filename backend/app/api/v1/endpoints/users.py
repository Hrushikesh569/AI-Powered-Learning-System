"""User profile endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Optional

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, UserProfile, ProgressLog, ScheduledTopic

router = APIRouter()

_get_user = get_current_user_dep()


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    studyHoursPerDay: Optional[float] = None
    learningGoal: Optional[str] = None
    grade: Optional[str] = None
    course: Optional[str] = None


async def _latest_profile_summary(db: AsyncSession, user_id: int) -> dict:
    result = await db.execute(
        select(UserProfile)
        .where(UserProfile.user_id == user_id)
        .order_by(UserProfile.updated_at.desc())
    )
    profile = result.scalar_one_or_none()
    features = profile.features if profile and isinstance(profile.features, dict) else {}
    return {
        "profileLabel": profile.profile_label if profile else "",
        "academicPerformance": features.get("academicPerformance") or features.get("performance") or "",
        "attendanceRate": features.get("attendanceRate") or "",
        "motivationLevel": features.get("motivationLevel") or features.get("motivation") or "",
        "learningStyle": features.get("learningStyle") or "",
    }


@router.get("/me")
async def get_me(current_user: User = Depends(_get_user), db: AsyncSession = Depends(get_db)):
    joined = current_user.created_at.isoformat() if current_user.created_at else None
    total_hours_result = await db.execute(
        select(func.coalesce(func.sum(ProgressLog.study_time), 0)).where(ProgressLog.user_id == current_user.id)
    )
    total_hours = float(total_hours_result.scalar_one() or 0)
    completed_sessions_result = await db.execute(
        select(func.count(ProgressLog.id)).where(ProgressLog.user_id == current_user.id)
    )
    completed_sessions = int(completed_sessions_result.scalar_one() or 0)
    profile_summary = await _latest_profile_summary(db, current_user.id)
    return {
        "id": current_user.id,
        "name": current_user.name or current_user.email.split("@")[0],
        "email": current_user.email,
        "grade": current_user.grade or "",
        "course": current_user.course or "",
        "branch": current_user.course or "",
        "studyHoursPerDay": current_user.study_hours_per_day or 2.0,
        "learningGoal": current_user.learning_goal or "",
        "learnerType": _learner_type(current_user.profile_cluster),
        "joinedDate": joined,
        "profileCluster": current_user.profile_cluster,
        "totalStudyHours": round(total_hours, 1),
        "completedSessions": completed_sessions,
        **profile_summary,
    }


@router.patch("/me")
async def update_me(
    payload: ProfileUpdate,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.name is not None:
        user.name = payload.name
    if payload.studyHoursPerDay is not None:
        user.study_hours_per_day = payload.studyHoursPerDay
    if payload.learningGoal is not None:
        user.learning_goal = payload.learningGoal
    if payload.grade is not None:
        user.grade = payload.grade
    if payload.course is not None:
        user.course = payload.course
    await db.commit()
    await db.refresh(user)

    progress_result = await db.execute(
        select(func.coalesce(func.sum(ProgressLog.study_time), 0)).where(ProgressLog.user_id == user.id)
    )
    total_hours = float(progress_result.scalar_one() or 0)
    session_result = await db.execute(
        select(func.count(ProgressLog.id)).where(ProgressLog.user_id == user.id)
    )
    completed_sessions = int(session_result.scalar_one() or 0)
    profile_summary = await _latest_profile_summary(db, user.id)

    return {
        "msg": "Profile updated",
        "name": user.name,
        "email": user.email,
        "grade": user.grade,
        "course": user.course,
        "branch": user.course,
        "studyHoursPerDay": user.study_hours_per_day,
        "learningGoal": user.learning_goal,
        "totalStudyHours": round(total_hours, 1),
        "completedSessions": completed_sessions,
        **profile_summary,
    }


def _learner_type(cluster: Optional[int]) -> str:
    mapping = {
        0: "High Achiever",
        1: "Consistent Learner",
        2: "Developing Learner",
        3: "At-Risk Learner",
        4: "Emerging Learner",
    }
    return mapping.get(cluster, "Baseline Learner")


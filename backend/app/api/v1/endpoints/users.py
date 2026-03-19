"""User profile endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User

router = APIRouter()

_get_user = get_current_user_dep()


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    studyHoursPerDay: Optional[float] = None
    learningGoal: Optional[str] = None


@router.get("/me")
async def get_me(current_user: User = Depends(_get_user)):
    joined = current_user.created_at.isoformat() if current_user.created_at else None
    return {
        "id": current_user.id,
        "name": current_user.name or current_user.email.split("@")[0],
        "email": current_user.email,
        "studyHoursPerDay": current_user.study_hours_per_day or 2.0,
        "learningGoal": current_user.learning_goal or "",
        "learnerType": _learner_type(current_user.profile_cluster),
        "joinedDate": joined,
        "profileCluster": current_user.profile_cluster,
        "totalStudyHours": 0,
        "completedSessions": 0,
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
    await db.commit()
    await db.refresh(user)
    return {"msg": "Profile updated", "name": user.name, "email": user.email}


def _learner_type(cluster: Optional[int]) -> str:
    mapping = {
        0: "High Achiever",
        1: "Consistent Learner",
        2: "Developing Learner",
        3: "At-Risk Learner",
        4: "Emerging Learner",
    }
    return mapping.get(cluster, "Baseline Learner")


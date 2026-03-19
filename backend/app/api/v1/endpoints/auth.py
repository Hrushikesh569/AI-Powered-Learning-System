"""Authentication endpoints — register, login."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime

from app.core.config import settings
from app.core.security import create_access_token, get_current_user_dep
from app.db.session import get_db
from app.db.models import User

router = APIRouter()
_get_user = get_current_user_dep()


class RegisterRequest(BaseModel):
    name: str = ""
    email: EmailStr
    password: str
    studyHoursPerDay: float = 2.0
    learningGoal: str = ""
    grade: str = ""
    course: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    email: str


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=_hash(payload.password),
        study_hours_per_day=payload.studyHoursPerDay,
        learning_goal=payload.learningGoal,
        grade=payload.grade,
        course=payload.course,
        created_at=datetime.now(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name or user.email.split("@")[0],
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user: User | None = result.scalar_one_or_none()

    if not user or not _verify(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name or user.email.split("@")[0],
        email=user.email,
    )


class ProfileUpdateRequest(BaseModel):
    name: str = None
    grade: str = None
    course: str = None
    study_hours_per_day: float = None
    study_start_hour: int = None
    study_end_hour: int = None
    learning_goal: str = None


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile information."""
    # Update only provided fields
    if payload.name is not None:
        current_user.name = payload.name
    if payload.grade is not None:
        current_user.grade = payload.grade
    if payload.course is not None:
        current_user.course = payload.course
    if payload.study_hours_per_day is not None:
        current_user.study_hours_per_day = max(0.5, min(12.0, payload.study_hours_per_day))
    if payload.study_start_hour is not None:
        current_user.study_start_hour = max(0, min(23, payload.study_start_hour))
    if payload.study_end_hour is not None:
        current_user.study_end_hour = max(1, min(24, payload.study_end_hour))
    if payload.learning_goal is not None:
        current_user.learning_goal = payload.learning_goal

    await db.commit()
    await db.refresh(current_user)

    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "grade": current_user.grade,
        "course": current_user.course,
        "study_hours_per_day": current_user.study_hours_per_day,
        "study_start_hour": current_user.study_start_hour,
        "study_end_hour": current_user.study_end_hour,
        "learning_goal": current_user.learning_goal,
        "message": "Profile updated successfully",
    }



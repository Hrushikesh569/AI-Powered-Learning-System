"""Authentication endpoints — register, login, and social auth."""
from datetime import datetime, timezone
import os
import re
from typing import Any, cast

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.messaging import phone_normalize
from app.core.security import create_access_token, get_current_user_dep
from app.db.session import get_db
from app.db.models import User, UserProfile

router = APIRouter()
_get_user = get_current_user_dep()


class RegisterRequest(BaseModel):
    name: str = ""
    email: EmailStr
    password: str
    phoneNumber: str | None = None
    studyHoursPerDay: float = 2.0
    learningGoal: str = ""
    grade: str = ""
    course: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=8)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class GoogleLoginRequest(BaseModel):
    id_token: str


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


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Password must include at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="Password must include at least one special character.")


async def _create_or_get_user_google(db: AsyncSession, *, email: str, name: str, google_sub: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user: Any = cast(Any, result.scalar_one_or_none())
    if user:
        user.auth_provider = 'google'
        user.google_sub = google_sub
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        if name and not user.name:
            user.name = name
        await db.commit()
        await db.refresh(user)
        return user

    user = User(
        email=email,
        name=name or email.split('@')[0],
        hashed_password=_hash(os.urandom(16).hex()),
        email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        auth_provider='google',
        google_sub=google_sub,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    _validate_password(payload.password)
    phone = phone_normalize(payload.phoneNumber)

    user: Any = User(
        email=payload.email,
        name=payload.name,
        hashed_password=_hash(payload.password),
        phone_number=phone or None,
        email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
        auth_provider='password',
        study_hours_per_day=payload.studyHoursPerDay,
        learning_goal=payload.learningGoal,
        grade=payload.grade,
        course=payload.course,
        created_at=datetime.now(timezone.utc),
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
    user: Any = cast(Any, result.scalar_one_or_none())

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


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Email verification is disabled for now.")


@router.post("/resend-verification")
async def resend_verification(payload: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Email verification is disabled for now.")


@router.post("/google", response_model=TokenResponse)
async def google_login(payload: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this server.")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": payload.id_token},
            )
        data = response.json() if response.status_code == 200 else {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google token verification failed: {exc}")

    if response.status_code != 200 or data.get("aud") != google_client_id:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    email = (data.get("email") or "").strip().lower()
    sub = (data.get("sub") or "").strip()
    name = (data.get("name") or data.get("given_name") or email.split("@")[0]).strip()
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Google token did not include a valid account email")

    user = await _create_or_get_user_google(db, email=email, name=name, google_sub=sub)
    user_data: Any = cast(Any, user)
    token = create_access_token({"sub": str(user_data.id), "email": str(user_data.email)})
    return TokenResponse(
        access_token=token,
        user_id=int(user_data.id),
        name=str(user_data.name or str(user_data.email).split("@")[0]),
        email=str(user_data.email),
    )


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    grade: str | None = None
    course: str | None = None
    study_hours_per_day: float | None = None
    study_start_hour: int | None = None
    study_end_hour: int | None = None
    learning_goal: str | None = None


async def _latest_profile_summary(db: AsyncSession, user_id: int) -> dict:
    result = await db.execute(
        select(UserProfile)
        .where(UserProfile.user_id == user_id)
        .order_by(UserProfile.updated_at.desc())
    )
    profile: Any = cast(Any, result.scalar_one_or_none())
    features = profile.features if profile and isinstance(profile.features, dict) else {}
    return {
        "profileLabel": profile.profile_label if profile else "",
        "academicPerformance": features.get("academicPerformance") or features.get("performance") or "",
        "attendanceRate": features.get("attendanceRate") or "",
        "motivationLevel": features.get("motivationLevel") or features.get("motivation") or "",
        "learningStyle": features.get("learningStyle") or "",
    }


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: Any = Depends(_get_user),
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

    profile_summary = await _latest_profile_summary(db, current_user.id)

    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "grade": current_user.grade,
        "course": current_user.course,
        "branch": current_user.course,
        "study_hours_per_day": current_user.study_hours_per_day,
        "study_start_hour": current_user.study_start_hour,
        "study_end_hour": current_user.study_end_hour,
        "learning_goal": current_user.learning_goal,
        **profile_summary,
        "message": "Profile updated successfully",
    }



"""Progress monitoring endpoint."""
import os
import joblib
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, ProgressLog

router = APIRouter()
_get_user = get_current_user_dep()

_ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "progress")
_models: dict = {}


def _load():
    if "model" not in _models:
        try:
            _models["model"]     = joblib.load(os.path.join(_ML_DIR, "lgb_model.pkl"))
            _models["scaler"]    = joblib.load(os.path.join(_ML_DIR, "scaler.pkl"))
            _models["threshold"] = joblib.load(os.path.join(_ML_DIR, "threshold.pkl"))
            _models["cont_cols"] = joblib.load(os.path.join(_ML_DIR, "cont_cols.pkl"))
        except Exception as e:
            raise RuntimeError(f"Progress models unavailable: {e}")


class ProgressFeatures(BaseModel):
    difficulty: float = 0.5
    u_cum_acc: float = 0.65
    u_roll5: float = 0.68
    u_total: int = 50
    attempt_n: int = 1
    q_cum_acc: float = 0.60
    irt_score: float = 0.0
    prev_correct: int = 1


@router.post("/predict")
async def predict_progress(
    features: ProgressFeatures,
    current_user: User = Depends(_get_user),
):
    try:
        _load()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # scaler.pkl is actually the cont_cols array; model needs 22 features (20 cont + user_cat + question_cat)
    model_cols = list(_models["model"].feature_name())
    feat_map = {
        "difficulty": features.difficulty,
        "u_cum_acc": features.u_cum_acc,
        "u_roll5": features.u_roll5,
        "u_total": float(features.u_total),
        "attempt_n": float(features.attempt_n),
        "q_cum_acc": features.q_cum_acc,
        "irt_score": features.irt_score,
        "prev_correct": float(features.prev_correct),
    }
    X_raw = np.array([[feat_map.get(c, 0.0) for c in model_cols]], dtype=float)
    prob = float(_models["model"].predict(X_raw)[0])
    threshold = float(_models["threshold"])
    return {
        "correct_probability": round(prob, 4),
        "prediction": int(prob >= threshold),
        "threshold": round(threshold, 4),
    }


@router.post("/log")
async def log_progress(
    request: Request,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    data = await request.json()
    db.add(ProgressLog(
        user_id=current_user.id,
        academic_metric=float(data.get("academic_metric", 0)),
        attendance=float(data.get("attendance", 0)),
        study_time=float(data.get("study_time", 0)),
    ))
    await db.commit()
    return {"msg": "Progress logged"}


@router.get("/dashboard")
async def get_progress_dashboard(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id)
        .order_by(ProgressLog.timestamp.desc())
        .limit(60)  # Get up to 60 days to calculate streak properly
    )
    logs = result.scalars().all()
    completed_hours = sum(l.study_time or 0 for l in logs)
    daily_goal = current_user.study_hours_per_day or 2.0
    total_hours = max(completed_hours * 1.5, daily_goal * 7)
    percentage = int(min(100, completed_hours / total_hours * 100)) if total_hours > 0 else 0
    
    # Calculate true consecutive day streak
    streak = _calculate_consecutive_streak(logs)

    # Generate personalized motivation based on grade/course level
    grade = (current_user.grade or "").strip().lower()
    course = (current_user.course or "").strip().lower()
    suggestions = _get_personalized_suggestions(grade, course, streak, completed_hours)
    quotes = _get_personalized_quotes(grade, course)

    return {
        "weeklyProgress": {
            "completedHours": round(completed_hours, 1),
            "totalHours": round(total_hours, 1),
            "streak": streak,
            "percentage": percentage,
        },
        "suggestions": suggestions,
        "motivationalQuotes": quotes,
        "achievements": [
            {
                "id": 1,
                "title": f"{streak}-Day Streak",
                "description": f"Studied for {streak} days in a row.",
                "icon": "fire",
                "unlocked": streak >= 3,
            },
            {
                "id": 2,
                "title": "First Session",
                "description": "Completed your first study session.",
                "icon": "star",
                "unlocked": len(logs) >= 1,
            },
        ],
    }


def _get_personalized_suggestions(grade: str, course: str, streak: int, hours: float):
    """Generate personalized study suggestions based on student profile."""
    # Determine student level: high school, undergrad, or advanced
    is_high_school = any(x in grade for x in ["grade", "9", "10", "11", "12"])
    is_advanced = any(x in grade for x in ["master", "phd", "grad", "postgrad", "year 3", "year 4"])
    is_stem = any(x in course for x in ["computer", "engineering", "math", "physics", "chemistry", "data"])
    
    suggestions = []
    
    # Base suggestions
    if streak == 0:
        suggestions.append({"id": 1, "message": "Start with just 20 minutes today — build momentum!", "action": "Begin Session"})
    elif streak < 3:
        suggestions.append({"id": 1, "message": f"You're building a habit! {streak} days in, aim for 7.", "action": "Continue"})
    else:
        suggestions.append({"id": 1, "message": f"Great consistency! You've got a {streak}-day streak.", "action": "Keep Going"})
    
    # Level-specific tips
    if is_high_school:
        if hours < 10:
            suggestions.append({"id": 2, "message": "Try the Pomodoro method: 25 min focus + 5 min break", "action": "Learn More"})
        else:
            suggestions.append({"id": 2, "message": "Excellent progress! Focus on practice problems for mastery.", "action": "View Tips"})
    elif is_advanced:
        if hours < 5:
            suggestions.append({"id": 2, "message": "Deep work requires uninterrupted focus. Block 90-minute sessions.", "action": "Schedule"})
        else:
            suggestions.append({"id": 2, "message": "You're logging solid hours. Review complex topics for depth.", "action": "Advanced Topics"})
    else:
        if hours < 7:
            suggestions.append({"id": 2, "message": "Mix active recall with spaced repetition for durable learning.", "action": "Learn Method"})
        else:
            suggestions.append({"id": 2, "message": "Strong work! Test yourself on harder problems.", "action": "Challenge"})
    
    # STEM-specific
    if is_stem:
        suggestions.append({"id": 3, "message": "Practice coding/problem-solving regularly — theory alone isn't enough.", "action": "Practice"})
    else:
        suggestions.append({"id": 3, "message": "Teach back what you learned—the best way to cement knowledge.", "action": "Explain"})
    
    return suggestions


def _get_personalized_quotes(grade: str, course: str):
    """Generate motivational quotes tailored to student level."""
    is_high_school = any(x in grade for x in ["grade", "9", "10", "11", "12"])
    is_stem = any(x in course for x in ["computer", "engineering", "math", "physics", "chemistry"])
    
    base_quotes = [
        "Small consistent sessions beat rare long ones.",
        "You are closer than you think—keep going.",
        "Progress, not perfection.",
    ]
    
    if is_high_school:
        extra = [
            "The pain of discipline weighs ounces; the pain of regret weighs tons.",
            "Future you will thank present you for studying today.",
        ]
    elif is_stem:
        extra = [
            "Bugs are features waiting to teach you something.",
            "The best code is the code you understand—not the shortest.",
        ]
    else:
        extra = [
            "Knowledge is the only treasure that grows when shared.",
            "Your curiosity is your superpower.",
        ]
    
    return base_quotes + extra


def _calculate_consecutive_streak(logs: list) -> int:
    """Calculate consecutive days of study activity.
    
    Args:
        logs: List of ProgressLog objects sorted by timestamp descending
        
    Returns:
        Number of consecutive days with at least 1 study session
    """
    if not logs:
        return 0
    
    from datetime import datetime, timedelta, timezone
    
    # Group logs by date, newest first
    dates_with_study = set()
    for log in logs:
        log_date = log.timestamp.replace(tzinfo=timezone.utc).date() if log.timestamp else None
        if log_date:
            dates_with_study.add(log_date)
    
    if not dates_with_study:
        return 0
    
    # Sort dates descending starting from today or most recent
    today = datetime.now(timezone.utc).date()
    sorted_dates = sorted(dates_with_study, reverse=True)
    
    streak = 0
    current_date = sorted_dates[0]
    
    # Count consecutive days backwards from most recent
    for i in range(len(sorted_dates)):
        expected_date = current_date - timedelta(days=i)
        if sorted_dates[i] == expected_date:
            streak += 1
        else:
            break
    
    # If streak doesn't include today and didn't include yesterday, reset to 0
    if streak > 0:
        most_recent_study_date = sorted_dates[0]
        if most_recent_study_date < today - timedelta(days=1):
            # Too old, streak is broken
            streak = 0
    
    return min(streak, 365)  # Cap at 1 year for display


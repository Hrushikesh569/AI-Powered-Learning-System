"""Profiling agent endpoint — assigns a cluster label to a user."""
import os
import joblib
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List, Dict, Any

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, UserProfile

router = APIRouter()
_get_user = get_current_user_dep()

# ML model paths
_ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "profiling")
_SCALER_PATH   = os.path.join(_ML_DIR, "scaler.pkl")
_KMEANS_PATH   = os.path.join(_ML_DIR, "kmeans.pkl")
_FEAT_PATH     = os.path.join(_ML_DIR, "feat_cols.pkl")

# Lazy-loaded models
_models: dict = {}

def _load_models():
    if "kmeans" not in _models:
        try:
            _models["scaler"]    = joblib.load(_SCALER_PATH)
            _models["kmeans"]    = joblib.load(_KMEANS_PATH)
            _models["feat_cols"] = joblib.load(_FEAT_PATH)
            _models["has_ml"] = True
        except Exception as e:
            # Fallback: Use heuristic-based profiling if models not found
            _models["has_ml"] = False


CLUSTER_NAMES = {
    0: "High Achiever",
    1: "Consistent Learner",
    2: "Developing Learner",
    3: "At-Risk Learner",
    4: "Emerging Learner",
}


class ProfileInput(BaseModel):
    """Minimal profiling input model."""
    grades: Optional[List[str]] = []
    studyHoursPerWeek: Optional[float] = 4.0  
    attendanceRate: Optional[float] = 80.0


class ProfileResponse(BaseModel):
    """Profiling response."""
    cluster: int
    profile_label: str
    features: Dict[str, Any]
    profiling_score: float


@router.post("/classify", response_model=ProfileResponse)
async def classify_profile(
    payload: ProfileInput,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Classify user learning profile based on actual performance metrics."""
    
    # Grade mapping: A=90, B=80, C=70, D=60, F=50
    grade_map = {'A': 90, 'B': 80, 'C': 70, 'D': 60, 'F': 50, 'A+': 95, 'A-': 85, 'B+': 85, 'B-': 75, 'C+': 75, 'C-': 65}
    
    # Calculate academic score from grades
    academic_score = 70.0  # default
    if payload.grades:
        valid_grades = [grade_map.get(g.upper().strip(), 70) for g in payload.grades if g]
        if valid_grades:
            academic_score = sum(valid_grades) / len(valid_grades)
    
    # Attendance score (0-100)
    attendance_score = max(0, min(100, payload.attendanceRate or 80.0))
    
    # Study hours score (convert to 0-100 scale: 0hrs=0, 5hrs=50, 10hrs=100)
    study_hours = payload.studyHoursPerWeek or 4.0
    study_score = min(100, max(0, (study_hours / 10.0) * 100))
    
    # Weighted composite score: 50% academics, 25% attendance, 25% study
    score = (academic_score * 0.50) + (attendance_score * 0.25) + (study_score * 0.25)
  
    # Cluster thresholds based on composite score
    if score >= 85:
        cluster = 0  # High Achiever
    elif score >= 70:
        cluster = 1  # Consistent Learner
    elif score >= 55:
        cluster = 2  # Developing Learner
    elif score >= 40:
        cluster = 3  # At-Risk Learner
    else:
        cluster = 4  # Emerging Learner
    
    # Save cluster to user in database
    current_user.profile_cluster = cluster
    db.add(current_user)
    await db.commit()
    
    return ProfileResponse(
        cluster=cluster,
        profile_label=CLUSTER_NAMES.get(cluster, f"Cluster {cluster}"),
        features=payload.model_dump(),
        profiling_score=round(score, 2)
    )

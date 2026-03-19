"""SHAP feature-importance explanations for the progress and profiling agents.

GET /explain/progress  → top-N SHAP contributions for the current user's last
                         progress-prediction input features
GET /explain/profile   → feature distances from cluster centroid for the
                         current user's profiling features (KMeans doesn't
                         support SHAP, so we use standardised centroid distance)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import joblib
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_current_user_dep
from app.db.models import AgentDecision, User, UserProfile
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()
_get_user = get_current_user_dep()

# ── Grade normalisation ───────────────────────────────────────────────────────
# Profiling models may be trained on numeric GPA values (0–4) but the stored
# UserProfile.features dict may hold letter-grade strings like 'B', 'A+', 'C-'.
_GRADE_GPA: dict[str, float] = {
    'a+': 4.0, 'a': 4.0, 'a-': 3.7,
    'b+': 3.3, 'b': 3.0, 'b-': 2.7,
    'c+': 2.3, 'c': 2.0, 'c-': 1.7,
    'd+': 1.3, 'd': 1.0, 'd-': 0.7,
    'f': 0.0,  'e': 0.0,
}


def _to_float(val) -> float:
    """Convert any feature value to float, mapping letter grades to GPA."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in _GRADE_GPA:
            return _GRADE_GPA[cleaned]
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0

# ── Model paths ─────────────────────────────────────────────────────────────

_PROGRESS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "progress")
_PROFILE_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "profiling")

_progress_cache: dict = {}
_profile_cache:  dict = {}


def _load_progress():
    if "model" not in _progress_cache:
        _progress_cache["model"]  = joblib.load(os.path.join(_PROGRESS_DIR, "lgb_model.pkl"))
        _progress_cache["scaler"] = joblib.load(os.path.join(_PROGRESS_DIR, "scaler.pkl"))
    return _progress_cache


def _load_profile():
    if "kmeans" not in _profile_cache:
        _profile_cache["kmeans"]    = joblib.load(os.path.join(_PROFILE_DIR, "kmeans.pkl"))
        _profile_cache["scaler"]    = joblib.load(os.path.join(_PROFILE_DIR, "scaler.pkl"))
        _profile_cache["feat_cols"] = joblib.load(os.path.join(_PROFILE_DIR, "feat_cols.pkl"))
    return _profile_cache


# ── Schemas ──────────────────────────────────────────────────────────────────

class FeatureContribution(BaseModel):
    feature: str
    value: float          # raw feature value
    impact: float         # SHAP value (positive = pushes toward positive class)
    direction: str        # "positive" | "negative"


class ExplanationResponse(BaseModel):
    agent: str
    contributions: list[FeatureContribution]
    summary: str
    model_used: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sign_label(v: float) -> str:
    return "positive" if v >= 0 else "negative"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/progress", response_model=ExplanationResponse)
async def explain_progress(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Return SHAP TreeExplainer values for the progress LightGBM model.

    Uses the user's most recent AgentDecision input_features, falling back to
    a sensible default vector when no history exists.
    """
    try:
        import shap
        models = _load_progress()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Progress model unavailable: {exc}")

    lgb_model = models["model"]
    feature_names: list[str] = list(lgb_model.feature_name())

    # Fetch the user's last progress-prediction decision (if any)
    result = await db.execute(
        select(AgentDecision)
        .where(AgentDecision.user_id == current_user.id)
        .where(AgentDecision.agent_name == "progress")
        .order_by(AgentDecision.timestamp.desc())
        .limit(1)
    )
    last_decision = result.scalar_one_or_none()

    if last_decision and last_decision.input_features:
        feat_dict: dict = last_decision.input_features
    else:
        # Use default values matching ProgressFeatures schema
        feat_dict = {
            "difficulty": 0.5, "u_cum_acc": 0.65, "u_roll5": 0.68,
            "u_total": 50.0, "attempt_n": 1.0, "q_cum_acc": 0.60,
            "irt_score": 0.0, "prev_correct": 1.0,
        }

    X = np.array([[feat_dict.get(f, 0.0) for f in feature_names]], dtype=float)

    try:
        explainer   = shap.TreeExplainer(lgb_model)
        shap_values = explainer.shap_values(X)
        # LightGBM binary classification: shap_values may be list [neg, pos]
        if isinstance(shap_values, list):
            sv = shap_values[1][0]
        else:
            sv = shap_values[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SHAP computation failed: {exc}")

    contributions = sorted(
        [
            FeatureContribution(
                feature=feature_names[i],
                value=round(float(X[0, i]), 4),
                impact=round(float(sv[i]), 4),
                direction=_sign_label(sv[i]),
            )
            for i in range(len(feature_names))
        ],
        key=lambda c: abs(c.impact),
        reverse=True,
    )[:8]  # top-8

    top = contributions[0] if contributions else None
    summary = (
        f"Your learning prediction is most influenced by **{top.feature}** "
        f"({'helping' if top.direction == 'positive' else 'hindering'} performance)."
        if top else "Insufficient data to determine key influences."
    )

    return ExplanationResponse(
        agent="progress",
        contributions=contributions,
        summary=summary,
        model_used="LightGBM (lgb_model.pkl)",
    )


@router.get("/profile", response_model=ExplanationResponse)
async def explain_profile(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """Explain the user's profile cluster via standardised centroid distances.

    KMeans does not produce SHAP values, so we compute how far each feature
    deviates from the assigned cluster centroid in the scaled feature space —
    features with the largest deviation are the ones that 'shaped' the cluster.
    """
    try:
        models = _load_profile()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Profile model unavailable: {exc}")

    kmeans    = models["kmeans"]
    scaler    = models["scaler"]
    feat_cols: list[str] = list(models["feat_cols"])

    # Fetch the most recent UserProfile for this user
    result = await db.execute(
        select(UserProfile)
        .where(UserProfile.user_id == current_user.id)
        .order_by(UserProfile.updated_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()

    if profile and profile.features:
        feat_dict = profile.features
    else:
        # Sensible academic defaults
        feat_dict = {
            "weekly_self_study_hours": 10.0,
            "attendance_percentage": 85.0,
            "class_participation": 3.0,
            "total_score": 75.0,
        }

    X_raw = np.array([[_to_float(feat_dict.get(f, 0.0)) for f in feat_cols]], dtype=float)
    X_scaled = scaler.transform(X_raw)

    cluster = int(kmeans.predict(X_scaled)[0])
    centroid = kmeans.cluster_centers_[cluster]

    deviations = X_scaled[0] - centroid   # positive = above centroid

    contributions = sorted(
        [
            FeatureContribution(
                feature=feat_cols[i],
                value=round(float(X_raw[0, i]), 4),
                impact=round(float(deviations[i]), 4),
                direction=_sign_label(deviations[i]),
            )
            for i in range(len(feat_cols))
        ],
        key=lambda c: abs(c.impact),
        reverse=True,
    )

    top = contributions[0] if contributions else None
    summary = (
        f"Your profile cluster is most driven by **{top.feature}** "
        f"(you are {'above' if top.direction == 'positive' else 'below'} the cluster average)."
        if top else "Profile not yet computed."
    )

    return ExplanationResponse(
        agent="profile",
        contributions=contributions,
        summary=summary,
        model_used="KMeans centroid-distance (profiling)",
    )

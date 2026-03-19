"""Motivation agent endpoint - classifies stress/motivation level."""
import os
import json
import joblib
import numpy as np
import lightgbm as lgb
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, MotivationLog

router = APIRouter()
_get_user = get_current_user_dep()

_ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "motivation")
_models: dict = {}

CATEGORY_LABELS = {0: "Low", 1: "Medium", 2: "High"}
INTERVENTIONS = {
    "Low":    ["Take a full rest day.", "Talk to your mentor.", "Reconnect with your learning goal."],
    "Medium": ["Try the Pomodoro technique.", "Short 5-min break, then back to it.", "Set one small win for today."],
    "High":   ["Keep up the great work!", "Share your progress with peers.", "Set a bigger challenge!"],
}


def _load():
    if "model" not in _models:
        try:
            lgb_path = os.path.join(_ML_DIR, "lgb_model.pkl")
            # Model was saved with bst.save_model() (native text format)
            try:
                _models["model"] = lgb.Booster(model_file=lgb_path)
            except Exception:
                _models["model"] = joblib.load(lgb_path)
            _models["scaler"]   = joblib.load(os.path.join(_ML_DIR, "scaler.pkl"))
            _models["le"]       = joblib.load(os.path.join(_ML_DIR, "label_encoder.pkl"))
            with open(os.path.join(_ML_DIR, "feat_defaults.json")) as f:
                meta = json.load(f)
            _models["feat_cols"] = meta["feat_cols"]
            _models["defaults"]  = meta["defaults"]
        except Exception as e:
            raise RuntimeError(f"Motivation models not found: {e}")


class MotivationInput(BaseModel):
    # Key user inputs; unmapped features get filled with training-set medians
    anxiety_level: float = None
    stress_level: float = None
    sleep_quality: float = None
    Study_Hours: float = None
    Sleep_Hours: float = None
    academic_performance: float = None
    social_support: float = None
    Physical_Exercise: float = None


@router.post("/classify")
async def classify_motivation(
    data: MotivationInput,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        _load()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Start from training-set medians then override with user inputs
    feat_vals = dict(_models["defaults"])
    overrides = data.model_dump(exclude_none=True)
    for k, v in overrides.items():
        if k in feat_vals:
            feat_vals[k] = float(v)

    X = np.array([[feat_vals[c] for c in _models["feat_cols"]]])
    X_scaled = _models["scaler"].transform(X)
    probs = _models["model"].predict(X_scaled)[0]  # shape (3,)
    pred_idx = int(np.argmax(probs))
    category = CATEGORY_LABELS.get(pred_idx, str(pred_idx))
    tips = INTERVENTIONS.get(category, INTERVENTIONS["Medium"])

    db.add(MotivationLog(
        user_id=current_user.id,
        motivation_score=float(probs[pred_idx] * 100),
        category=category,
        intervention=tips[0],
    ))
    await db.commit()

    return {"category": category, "tips": tips, "confidence": round(float(probs[pred_idx]), 4)}


@router.get("/tips")
async def get_motivation_tips(current_user: User = Depends(_get_user)):
    return {
        "tips": [
            "Consistency beats intensity - show up every day.",
            "Break big goals into 25-min focused blocks.",
            "Reward yourself after completing a session.",
            "Track your streak - it motivates more than you think.",
            "Sleep 7-8 hours: memory consolidation happens at night.",
        ]
    }


@router.post("/log")
async def log_motivation(
    data: MotivationInput,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    db.add(MotivationLog(
        user_id=current_user.id,
        motivation_score=float(data.stress_level or 5.0) * 10,
        category="logged",
        intervention="",
    ))
    await db.commit()
    return {"msg": "Motivation logged"}

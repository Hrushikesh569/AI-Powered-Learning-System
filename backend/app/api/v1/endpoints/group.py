"""Group matching endpoint — assigns a student to a study group."""
import os
import joblib
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, GroupMembership, GroupData

router = APIRouter()
_get_user = get_current_user_dep()

_ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "group")
_models: dict = {}


def _load():
    if "kmeans" not in _models:
        try:
            _models["scaler"]    = joblib.load(os.path.join(_ML_DIR, "scaler.pkl"))
            _models["kmeans"]    = joblib.load(os.path.join(_ML_DIR, "kmeans.pkl"))
            _models["feat_cols"] = joblib.load(os.path.join(_ML_DIR, "feat_cols.pkl"))
        except Exception as e:
            raise RuntimeError(f"Group models not found: {e}")


GROUP_NAMES = {
    0: "Alpha Learners",
    1: "Beta Crew",
    2: "Rising Stars",
    3: "Support Circle",
    4: "Explorer Group",
}


class GroupMatchRequest(BaseModel):
    grade: str = "B"  # A/B/C/D/F


@router.post("/match")
async def match_group(
    payload: GroupMatchRequest,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        _load()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    grade_map = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
    grade_enc = grade_map.get(payload.grade.upper(), 1)
    feat_cols = _models["feat_cols"]
    feat_map = {"grade": float(grade_enc)}
    X = np.array([[feat_map.get(c, 0.0) for c in feat_cols]])
    X_scaled = _models["scaler"].transform(X)
    group_id = int(_models["kmeans"].predict(X_scaled)[0])
    group_name = GROUP_NAMES.get(group_id, f"Group {group_id}")

    return {
        "group_id": group_id,
        "group_name": group_name,
        "description": f"You have been matched to the {group_name} based on your academic profile.",
    }


@router.get("/my-group")
async def get_my_group(current_user: User = Depends(_get_user)):
    cluster = current_user.profile_cluster
    if cluster is None:
        return {"group": None, "message": "Complete profiling first"}
    return {
        "group_id": cluster,
        "group_name": GROUP_NAMES.get(cluster, f"Group {cluster}"),
    }


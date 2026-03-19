"""Stress logging endpoint."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, StressLog

router = APIRouter()
_get_user = get_current_user_dep()


class StressData(BaseModel):
    stress_level: float = 5.0   # 1-10
    sleep_hours: float = 7.0
    physical_activity: float = 30.0  # minutes


@router.post("/log")
async def log_stress(
    data: StressData,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    db.add(StressLog(
        user_id=current_user.id,
        stress_level=data.stress_level,
        sleep_hours=data.sleep_hours,
        physical_activity=data.physical_activity,
    ))
    await db.commit()
    return {"msg": "Stress data logged", "stress_level": data.stress_level}


@router.get("/analysis")
async def get_stress_analysis(current_user: User = Depends(_get_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    result = await db.execute(
        select(StressLog)
        .where(StressLog.user_id == current_user.id)
        .order_by(StressLog.timestamp.desc())
        .limit(7)
    )
    logs = result.scalars().all()
    if not logs:
        return {"average_stress": 5.0, "trend": "neutral", "recommendation": "No data yet."}
    avg = sum(l.stress_level for l in logs) / len(logs)
    trend = "improving" if len(logs) > 1 and logs[0].stress_level < logs[-1].stress_level else "stable"
    rec = "Great job managing stress!" if avg < 4 else "Consider reducing workload." if avg > 7 else "You're doing well."
    return {"average_stress": round(avg, 1), "trend": trend, "recommendation": rec}


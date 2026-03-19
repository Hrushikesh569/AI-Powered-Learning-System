from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core import alerts as alerts_core

router = APIRouter()


class AlertCreate(BaseModel):
    run_id: str
    metric_key: str
    operator: str  # gt, ge, lt, le
    threshold: float
    notify_url: Optional[str] = None
    cooldown_seconds: Optional[int] = 3600
    notify_email: Optional[str] = None


@router.get('/')
def list_alerts():
    return alerts_core.load_alerts()


@router.post('/')
def create_alert(req: AlertCreate):
    a = req.dict()
    saved = alerts_core.add_alert(a)
    return saved


@router.delete('/{alert_id}')
def delete_alert(alert_id: str):
    ok = alerts_core.delete_alert(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Alert not found')
    return {'status': 'deleted'}


@router.post('/check')
def trigger_check():
    # Trigger a synchronous check (Celery task exists for scheduled runs)
    triggered = alerts_core.check_alerts()
    return {'triggered': triggered}

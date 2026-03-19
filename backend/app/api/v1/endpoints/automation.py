from fastapi import APIRouter
from pydantic import BaseModel
from app.core.automation import retrain_all_agents_task, evaluate_agent_task

router = APIRouter()


class EvalRequest(BaseModel):
    agent: str = 'schedule'
    runs: int = 50
    state_dim: int = 8


@router.post("/retrain")
def retrain_agents():
    retrain_all_agents_task.delay()
    return {"status": "Retraining started"}


@router.post("/evaluate")
def evaluate_agent(req: EvalRequest):
    evaluate_agent_task.delay(req.agent, req.runs, req.state_dim)
    return {"status": "Evaluation started", "agent": req.agent, "runs": req.runs}

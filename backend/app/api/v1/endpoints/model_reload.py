from fastapi import APIRouter
from app.core.model_hot_reload import reload_all_agents

router = APIRouter()

@router.post("/reload")
def reload_models():
    reload_all_agents()
    return {"status": "All agent models hot-reloaded"}

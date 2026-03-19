from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import (
    users, profiling, schedule, progress, stress, motivation,
    community, group, auth, automation, model_reload, content,
    evaluations, alerts, explain
)
from app.core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Auto-create all DB tables on startup (idempotent)
    from app.db.session import init_db
    await init_db()
    yield


app = FastAPI(title="AI-Powered Learning Backend", version="1.0", lifespan=lifespan)

# CORS configured for both development and production
if settings.ENVIRONMENT == "development":
    allowed_origins = ["*"]
else:
    allowed_origins = ["https://yourdomain.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

# Routers
app.include_router(auth.router,         prefix="/api/v1/auth",        tags=["auth"])
app.include_router(users.router,        prefix="/api/v1/users",       tags=["users"])
app.include_router(profiling.router,    prefix="/api/v1/profiling",   tags=["profiling"])
app.include_router(schedule.router,     prefix="/api/v1/schedule",    tags=["schedule"])
app.include_router(progress.router,     prefix="/api/v1/progress",    tags=["progress"])
app.include_router(stress.router,       prefix="/api/v1/stress",      tags=["stress"])
app.include_router(motivation.router,   prefix="/api/v1/motivation",  tags=["motivation"])
app.include_router(community.router,    prefix="/api/v1/community",   tags=["community"])
app.include_router(group.router,        prefix="/api/v1/group",       tags=["group"])
app.include_router(automation.router,   prefix="/api/v1/automation",  tags=["automation"])
app.include_router(model_reload.router, prefix="/api/v1/model",       tags=["model"])
app.include_router(content.router,      prefix="/api/v1/content",     tags=["content"])
app.include_router(evaluations.router,  prefix="/api/v1/evaluations", tags=["evaluations"])
app.include_router(alerts.router,       prefix="/api/v1/alerts",      tags=["alerts"])
app.include_router(explain.router,      prefix="/api/v1/explain",     tags=["explain"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0"}


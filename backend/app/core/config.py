import os
from pydantic_settings import BaseSettings

# Resolve project root (backend/)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SQLITE_PATH = os.path.join(_BACKEND_DIR, "ai_learning.db")
_SQLITE_URL   = f"sqlite+aiosqlite:///{_SQLITE_PATH}"

# Accept either POSTGRES_URL or DATABASE_URL (Render/Railway/Heroku standard)
_DB_DEFAULT = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or _SQLITE_URL

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Powered Learning Backend"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    # Populated from POSTGRES_URL env var; falls back to DATABASE_URL, then SQLite
    POSTGRES_URL: str = _DB_DEFAULT
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32-chars!")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    ML_MODEL_REGISTRY: str = os.getenv("ML_MODEL_REGISTRY", "mlruns")

settings = Settings()

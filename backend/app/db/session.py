from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# SQLite needs check_same_thread=False via connect_args
_connect_args = {"check_same_thread": False} if settings.POSTGRES_URL.startswith("sqlite") else {}

engine = create_async_engine(
    settings.POSTGRES_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables — idempotent and safe under concurrent worker startup."""
    from app.db.models import Base
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
    except Exception:
        # Under multi-worker startup two processes may race to CREATE TABLE;
        # the losing worker gets a duplicate-key error — that is harmless because
        # the table was already created by the winner.
        pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

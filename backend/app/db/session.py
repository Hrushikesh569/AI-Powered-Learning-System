from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect, text
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
            await conn.run_sync(_sync_user_schema)
    except Exception:
        # Under multi-worker startup two processes may race to CREATE TABLE;
        # the losing worker gets a duplicate-key error — that is harmless because
        # the table was already created by the winner.
        pass


def _sync_user_schema(connection):
    """Backfill newly added auth columns on existing databases."""
    inspector = inspect(connection)
    if not inspector.has_table('users'):
        return

    existing_columns = {column['name'] for column in inspector.get_columns('users')}
    additions = {
        'phone_number': "ALTER TABLE users ADD COLUMN phone_number VARCHAR",
        'email_verified': "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0",
        'email_verified_at': "ALTER TABLE users ADD COLUMN email_verified_at DATETIME",
        'auth_provider': "ALTER TABLE users ADD COLUMN auth_provider VARCHAR DEFAULT 'password'",
        'google_sub': "ALTER TABLE users ADD COLUMN google_sub VARCHAR",
        'email_notifications_enabled': "ALTER TABLE users ADD COLUMN email_notifications_enabled BOOLEAN DEFAULT 1",
        'sms_notifications_enabled': "ALTER TABLE users ADD COLUMN sms_notifications_enabled BOOLEAN DEFAULT 0",
    }

    for column_name, statement in additions.items():
        if column_name not in existing_columns:
            connection.execute(text(statement))

    connection.execute(text("UPDATE users SET email_verified = COALESCE(email_verified, 1)"))
    connection.execute(text("UPDATE users SET auth_provider = COALESCE(auth_provider, 'password')"))
    connection.execute(text("UPDATE users SET email_notifications_enabled = COALESCE(email_notifications_enabled, 1)"))
    connection.execute(text("UPDATE users SET sms_notifications_enabled = COALESCE(sms_notifications_enabled, 0)"))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

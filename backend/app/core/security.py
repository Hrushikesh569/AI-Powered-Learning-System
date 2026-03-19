from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.core.config import settings
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import re
import logging

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: int = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = None,
):
    """Decode JWT and return the User ORM object."""
    from app.db.models import User
    from app.db.session import get_db

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    # We need a real DB session; use dependency injection helpers
    return {"user_id": int(user_id), "email": payload.get("email")}


def get_current_user_dep():
    """Returns a FastAPI Depends-compatible coroutine that resolves the current user."""
    async def _inner(token: str = Depends(oauth2_scheme)):
        from app.db.models import User
        from app.db.session import AsyncSessionLocal
        from sqlalchemy.future import select as sa_select

        credentials_exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if not token:
            raise credentials_exc
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id_str: str = payload.get("sub")
            if user_id_str is None:
                raise credentials_exc
        except JWTError:
            raise credentials_exc

        async with AsyncSessionLocal() as session:
            result = await session.execute(sa_select(User).where(User.id == int(user_id_str)))
            user = result.scalar_one_or_none()
            if user is None:
                raise credentials_exc
            return user
    return _inner


def mask_pii(data: dict) -> dict:
    masked = {}
    for k, v in data.items():
        if isinstance(v, str) and re.match(r"[^@]+@[^@]+\.[^@]+", v):
            masked[k] = v[0] + "***" + v[-1]
        else:
            masked[k] = v
    return masked


def audit_log(event: str, user_id: int = None, details: dict = None):
    logging.info(f"AUDIT | {datetime.utcnow()} | user={user_id} | {event} | {details}")


def validate_input(data: dict, required_fields: list):
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")


def check_gdpr_rights(user_id: int):
    pass


def rate_limit(request: Request, max_per_minute=60):
    pass


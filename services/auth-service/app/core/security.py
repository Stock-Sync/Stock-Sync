import bcrypt
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    # bcrypt has a 72 byte limit, truncate if necessary
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    plain_bytes = plain.encode("utf-8")[:72]
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def create_access_token(subject: str, tenant_id: str | int, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode: dict[str, Any] = {"sub": subject, "tenant_id": str(tenant_id), "type": "access", "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, tenant_id: str | int, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days))
    to_encode: dict[str, Any] = {"sub": subject, "tenant_id": str(tenant_id), "type": "refresh", "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.JWTError:
        raise ValueError("Invalid token")


def get_token_type(payload: dict[str, Any]) -> str:
    return payload.get("type", "")
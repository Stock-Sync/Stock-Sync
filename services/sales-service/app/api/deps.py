"""Shared API dependencies."""

from fastapi import Header, HTTPException

from app.core.config import settings


def require_internal_secret(
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """Guard service-to-service endpoints with a shared secret header."""
    if not x_internal_secret or x_internal_secret != settings.internal_service_secret:
        raise HTTPException(status_code=401, detail="Invalid internal service secret")

"""Shared API dependencies for sync-service.

Public routes (frontend) use the auth-service access token. Operational routes
that act on global state (dead-letter replay) use the internal shared secret.
"""

import hmac

from fastapi import Header, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import settings

_UNAUTHORIZED_DETAIL = "Tenant ID not found"


def _tenant_from_access_token(token: str) -> str | None:
    """Decode an auth-service token and return its tenant when it is an access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    tenant_id = payload.get("tenant_id")
    return str(tenant_id) if tenant_id else None


def get_tenant_id(request: Request) -> str:
    """Resolve the tenant from the access token (cookie or Bearer header).

    The legacy ``tenant_id`` cookie and a standalone ``X-Tenant-ID`` header are
    never trusted.
    """
    access_token = request.cookies.get("access_token")
    if access_token:
        tenant_id = _tenant_from_access_token(access_token)
        if tenant_id:
            return tenant_id

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        tenant_id = _tenant_from_access_token(authorization[len("Bearer ") :])
        if tenant_id:
            return tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED_DETAIL,
    )


def require_internal_secret(
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """Guard operational service-to-service endpoints with the shared secret."""
    if not x_internal_secret or not hmac.compare_digest(
        x_internal_secret, settings.internal_service_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid internal service secret")

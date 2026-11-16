"""Shared API dependencies for public and internal integrations endpoints.

Public routes (called by the frontend) derive the tenant from the auth-service
access token. Internal routes (called by sync-service) require the shared
secret and an explicit ``X-Tenant-ID`` header. A standalone ``X-Tenant-ID`` is
never trusted.
"""

import hmac

from fastapi import Depends, Header, HTTPException, Request, status
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
    """Resolve the tenant of a public request from a signed access token.

    Accepts ``Authorization: Bearer`` or the ``access_token`` cookie. Refresh
    tokens and the legacy ``tenant_id`` cookie are rejected.
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
    """Guard service-to-service endpoints with a shared secret header."""
    if not x_internal_secret or not hmac.compare_digest(
        x_internal_secret, settings.internal_service_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid internal service secret")


def get_internal_tenant_id(
    x_tenant_id: str | None = Header(default=None),
    _: None = Depends(require_internal_secret),
) -> str:
    """Resolve the tenant of an internal request (valid secret + X-Tenant-ID)."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHORIZED_DETAIL,
        )
    return x_tenant_id

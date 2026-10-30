"""Dependencies shared across catalog-service routes.

Resolves the current tenant from the authenticated request, mirroring the
contract used by integrations-service and sync-service so a single tenant_id
is enforced everywhere.
"""

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import settings


def get_tenant_id(request: Request) -> str:
    """Extract tenant_id from an authenticated request.

    Priority:
    1. X-Tenant-ID header (service-to-service calls)
    2. tenant_id cookie (explicit)
    3. access_token cookie (JWT from auth-service) - decode JWT
    4. Authorization: Bearer header (fallback; http-client sends the token here)
    """
    # 1. Header (service-to-service)
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    # 2. Explicit tenant_id cookie
    tenant_id = request.cookies.get("tenant_id")
    if tenant_id:
        return tenant_id

    # 3. Extract from access_token cookie (JWT from auth-service)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = jwt.decode(
                access_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return tenant_id
        except JWTError:
            pass  # Invalid token, continue to next method

    # 4. Fallback: Authorization: Bearer header
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return tenant_id
        except JWTError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tenant ID not found",
    )


def get_current_tenant(tenant_id: str = Depends(get_tenant_id)) -> str:
    """Alias for clarity in route signatures."""
    return tenant_id

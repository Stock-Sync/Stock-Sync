"""Dependencies shared across catalog-service routes.

The catalog serves two kinds of callers:

* the frontend, authenticated by the auth-service JWT (``access_token`` cookie
  or ``Authorization: Bearer``);
* sibling services (sync-service), authenticated by the internal shared secret
  plus the ``X-Tenant-ID`` header.

``get_tenant_id`` is therefore hybrid: the presence of ``X-Internal-Secret``
selects the internal path, otherwise the request must carry a valid access
token. An isolated ``X-Tenant-ID`` header is never trusted.
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


def _tenant_from_public_request(request: Request) -> str | None:
    """Resolve the tenant from the cookie or the Authorization: Bearer header."""
    access_token = request.cookies.get("access_token")
    if access_token:
        tenant_id = _tenant_from_access_token(access_token)
        if tenant_id:
            return tenant_id

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return _tenant_from_access_token(authorization[len("Bearer ") :])

    return None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED_DETAIL,
    )


def get_tenant_id(request: Request) -> str:
    """Resolve the tenant for public (JWT) and internal (secret + header) calls.

    * ``X-Internal-Secret`` present: the internal path is used and the secret
      must be valid; ``X-Tenant-ID`` is then required.
    * otherwise: only a signed access token is accepted. The legacy
      ``tenant_id`` cookie and a standalone ``X-Tenant-ID`` are rejected.
    """
    internal_secret = request.headers.get("X-Internal-Secret")
    if internal_secret is not None:
        if not hmac.compare_digest(internal_secret, settings.internal_service_secret):
            raise _unauthorized()
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise _unauthorized()
        return tenant_id

    tenant_id = _tenant_from_public_request(request)
    if tenant_id:
        return tenant_id

    raise _unauthorized()


def get_current_tenant(tenant_id: str = Depends(get_tenant_id)) -> str:
    """Alias for clarity in route signatures."""
    return tenant_id


def require_internal_secret(
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """Guard strict service-to-service endpoints with the shared secret."""
    if not x_internal_secret or not hmac.compare_digest(
        x_internal_secret, settings.internal_service_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service secret",
        )


def get_internal_tenant_id(
    x_tenant_id: str | None = Header(default=None),
    _: None = Depends(require_internal_secret),
) -> str:
    """Resolve the tenant of an internal request (valid secret + X-Tenant-ID)."""
    if not x_tenant_id:
        raise _unauthorized()
    return x_tenant_id

"""Tenant contract tests for the catalog hybrid dependency."""

import pytest
from app.api.deps import get_tenant_id
from app.core.config import settings
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

INTERNAL_SECRET = settings.internal_service_secret


def _request(
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    return Request({"type": "http", "headers": raw_headers})


def _token(tenant_id: str = "tenant-1", token_type: str = "access") -> str:
    return jwt.encode(
        {"tenant_id": tenant_id, "type": token_type},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def test_standalone_tenant_header_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_id(_request(headers={"X-Tenant-ID": "tenant-1"}))
    assert exc.value.status_code == 401


def test_internal_secret_plus_tenant_is_accepted():
    request = _request(
        headers={
            "X-Internal-Secret": INTERNAL_SECRET,
            "X-Tenant-ID": "tenant-1",
        }
    )
    assert get_tenant_id(request) == "tenant-1"


def test_internal_secret_without_tenant_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_id(_request(headers={"X-Internal-Secret": INTERNAL_SECRET}))
    assert exc.value.status_code == 401


def test_wrong_internal_secret_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_id(
            _request(
                headers={
                    "X-Internal-Secret": "wrong",
                    "X-Tenant-ID": "tenant-1",
                }
            )
        )
    assert exc.value.status_code == 401


def test_access_token_cookie_is_accepted():
    request = _request(cookies={"access_token": _token()})
    assert get_tenant_id(request) == "tenant-1"


def test_bearer_access_token_is_accepted():
    request = _request(headers={"Authorization": f"Bearer {_token()}"})
    assert get_tenant_id(request) == "tenant-1"


def test_refresh_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_id(_request(cookies={"access_token": _token(token_type="refresh")}))
    assert exc.value.status_code == 401


def test_legacy_tenant_cookie_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_id(_request(cookies={"tenant_id": "tenant-1"}))
    assert exc.value.status_code == 401

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_type,
    hash_password,
    verify_password,
)
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    cookie_kwargs = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain if settings.cookie_domain != "localhost" else None,
    }
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        **cookie_kwargs,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        path="/",
        **cookie_kwargs,
    )


def clear_auth_cookies(response: Response) -> None:
    cookie_kwargs = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain if settings.cookie_domain != "localhost" else None,
    }
    response.delete_cookie(key="access_token", path="/", **cookie_kwargs)
    response.delete_cookie(key="refresh_token", path="/", **cookie_kwargs)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> RegisterResponse:
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise ConflictError("Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return RegisterResponse(user_id=user.id)


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, session: Session = Depends(get_session)) -> UserResponse:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid credentials")

    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")

    access_token = create_access_token(subject=user.email, tenant_id=user.id)
    refresh_token = create_refresh_token(subject=user.email, tenant_id=user.id)

    set_auth_cookies(response, access_token, refresh_token)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


@router.post("/refresh", response_model=UserResponse)
def refresh(response: Response, request: Request, session: Session = Depends(get_session)) -> UserResponse:
    from fastapi import Request

    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        clear_auth_cookies(response)
        raise UnauthorizedError("Refresh token not found")

    try:
        payload = decode_token(refresh_token)
    except ValueError as e:
        clear_auth_cookies(response)
        raise UnauthorizedError(str(e))

    if get_token_type(payload) != "refresh":
        clear_auth_cookies(response)
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("tenant_id")
    user = session.get(User, user_id)
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise UnauthorizedError("User not found or inactive")

    access_token = create_access_token(subject=user.email, tenant_id=user.id)
    new_refresh_token = create_refresh_token(subject=user.email, tenant_id=user.id)

    set_auth_cookies(response, access_token, new_refresh_token)

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


@router.post("/logout", response_model=dict)
def logout(response: Response) -> dict:
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(request: Request, session: Session = Depends(get_session)) -> UserResponse:
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise UnauthorizedError("Access token not found")

    try:
        payload = decode_token(access_token)
    except ValueError as e:
        raise UnauthorizedError(str(e))

    if get_token_type(payload) != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("tenant_id")
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from redis.exceptions import RedisError
from sqlmodel import Session

from app.api.deps import get_tenant_id
from app.core.config import settings
from app.db.session import get_session
from app.services.mercadolibre import MercadoLivreService
from app.services.oauth_state import (
    OAuthStateError,
    consume_oauth_state,
    create_oauth_state,
)

router = APIRouter(prefix="/api/v1/auth/mercadolivre", tags=["mercadolivre-auth"])


def _oauth_cookie_params() -> dict:
    """Derive cookie attributes for the OAuth state binding cookie.

    The cookie is scoped to the OAuth path so it is not sent on unrelated
    API calls. When the public API is HTTPS and its hostname differs from the
    frontend (cross-site redirect via Mercado Livre), ``secure=True`` and
    ``samesite="none"`` are required so the cookie survives the top-level
    navigation back to the public API. On same-site deployments, ``samesite``
    is ``lax`` and ``secure`` follows the public API's scheme.

    Returns the subset of attributes safe for both ``set_cookie`` and
    ``delete_cookie`` (excludes ``max_age``, which ``delete_cookie`` does not
    accept).
    """
    public_host = settings.public_api_url.split("://", 1)[-1].split("/", 1)[0]
    frontend_host = settings.frontend_url.split("://", 1)[-1].split("/", 1)[0]
    is_https = settings.public_api_url.startswith("https://")

    if is_https and public_host != frontend_host:
        samesite = "none"
        secure = True
    else:
        samesite = "lax"
        secure = is_https

    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "path": "/api/v1/auth/mercadolivre",
    }


@router.get("/connect")
async def ml_connect(
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_session),
):
    """Generate Mercado Livre OAuth URL for the authenticated tenant.

    The raw tenant is no longer used as the ``state``: a signed, single-use
    nonce is issued and stored in Redis for the callback. An HttpOnly cookie
    holding the HMAC-SHA256 digest of the nonce is set on the response so the
    state is bound to the initiating browser session (Plan 14).
    """
    ml_service = MercadoLivreService(session)
    try:
        state, cookie_digest = await create_oauth_state(tenant_id)
    except RedisError:
        raise HTTPException(
            status_code=503,
            detail="OAuth state store unavailable",
        ) from None

    auth_url = ml_service.get_auth_url(state)

    response = {
        "auth_url": auth_url,
        "tenant_id": tenant_id,
    }
    # Attach the binding cookie to the JSON response so the browser persists it.
    # The cookie is set via a separate Set-Cookie header by returning a
    # JSONResponse with cookie support.
    from fastapi.responses import JSONResponse

    json_response = JSONResponse(content=response)
    json_response.set_cookie(
        key=settings.oauth_state_cookie_name,
        value=cookie_digest,
        max_age=settings.oauth_state_ttl_seconds,
        **_oauth_cookie_params(),
    )
    return json_response


@router.get("/callback")
async def ml_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
):
    """Handle Mercado Livre OAuth callback.

    The state must have a valid signature/audience/type/expiration and its
    nonce must still be present in Redis (``GETDEL`` makes it single-use).
    The HttpOnly cookie set on ``/connect`` is validated against the decoded
    nonce *before* the nonce is consumed, binding the state to the browser
    that initiated the flow (Plan 14). The cookie is deleted on the redirect
    response after successful validation.
    """
    cookie_digest = request.cookies.get(settings.oauth_state_cookie_name)

    try:
        tenant_id = await consume_oauth_state(state, cookie_digest)
    except OAuthStateError:
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired or already used OAuth state",
        ) from None
    except RedisError:
        raise HTTPException(
            status_code=503,
            detail="OAuth state store unavailable",
        ) from None

    ml_service = MercadoLivreService(session)

    # Exchange code for tokens
    token_data = await ml_service.exchange_code_for_tokens(code, tenant_id)

    # Get user info to extract ml_user_id
    user_info = await ml_service.get_user_info(token_data["access_token"])

    # Save credential
    ml_service.save_credential(tenant_id, token_data, user_info)

    # Webhook topics and the callback URL are configured in the Mercado Livre
    # app manager (applications.mercadolibre.com); ML exposes no subscription
    # API (api.mercadolibre.com/webhooks returns 404).
    redirect_target = f"{settings.frontend_url.rstrip('/')}/#/integrations?connected=mercadolivre"
    redirect_response = RedirectResponse(url=redirect_target, status_code=307)
    redirect_response.delete_cookie(
        key=settings.oauth_state_cookie_name,
        **_oauth_cookie_params(),
    )
    return redirect_response

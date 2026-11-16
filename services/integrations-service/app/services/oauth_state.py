"""Signed, single-use OAuth state for the Mercado Livre connect flow.

The state is a short-lived JWT signed with the shared ``JWT_SECRET_KEY`` and
carries the tenant plus a random nonce. The nonce is also stored in Redis and
consumed with ``GETDEL`` on the callback, so a state can only be used once.

Plan 14 additionally binds the state to an HttpOnly browser cookie set on
``GET /connect`` and validated on ``GET /callback``. The raw nonce inside the
JWT is never exposed directly in the cookie; instead an HMAC-SHA256 hex digest
(keyed with ``JWT_SECRET_KEY``) of the nonce is stored as the cookie value.
On callback, the cookie digest is compared in constant time against the digest
derived from the decoded nonce *before* the Redis nonce is consumed, so an
attacker without the initiating browser's cookie cannot burn a pending state.

Validation checks the signature, audience, type and expiration before the
authorization code is exchanged.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import settings
from app.core.redis import pop_oauth_state, save_oauth_state

OAUTH_STATE_AUDIENCE = "stocksync:mercadolivre-oauth"
OAUTH_STATE_TYPE = "oauth_state"


class OAuthStateError(ValueError):
    """Raised when a state is missing, tampered, expired or already used."""


def hash_oauth_nonce(nonce: str) -> str:
    """Return an HMAC-SHA256 hex digest of ``nonce`` keyed with ``jwt_secret_key``.

    The digest binds the OAuth state to the browser session cookie without
    exposing the raw nonce.
    """
    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        nonce.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def create_oauth_state(
    tenant_id: str,
) -> tuple[str, str]:
    """Build a signed state and persist its nonce for single use.

    Returns ``(state, cookie_digest)`` where ``cookie_digest`` is the
    HMAC-SHA256 of the nonce that must be stored in an HttpOnly cookie on the
    initiating browser and validated on callback.

    Redis failures propagate so the route can return 503 (the flow must not
    start if the state cannot be validated on the callback).
    """
    ttl = settings.oauth_state_ttl_seconds
    nonce = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    payload = {
        "tenant_id": str(tenant_id),
        "nonce": nonce,
        "aud": OAUTH_STATE_AUDIENCE,
        "type": OAUTH_STATE_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    state = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    await save_oauth_state(nonce, str(tenant_id), ttl)
    cookie_digest = hash_oauth_nonce(str(nonce))
    return state, cookie_digest


async def consume_oauth_state(
    state: str,
    cookie_digest: str | None,
) -> str:
    """Validate a state and return its tenant, consuming the nonce.

    The ``cookie_digest`` from the initiating browser's HttpOnly cookie is
    verified in constant time against the digest derived from the decoded
    nonce *before* the Redis nonce is consumed. This binds the state to the
    browser that initiated the flow, preventing CSRF.

    Raises :class:`OAuthStateError` for any invalid state and lets Redis errors
    propagate so the caller can distinguish an authentication failure (400)
    from an infrastructure failure (503).
    """
    if cookie_digest is None:
        raise OAuthStateError("Missing OAuth session binding cookie")

    try:
        payload = jwt.decode(
            state,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=OAUTH_STATE_AUDIENCE,
        )
    except JWTError as exc:
        raise OAuthStateError("Invalid or expired OAuth state") from exc

    if payload.get("type") != OAUTH_STATE_TYPE:
        raise OAuthStateError("Invalid OAuth state type")

    nonce = payload.get("nonce")
    tenant_id = payload.get("tenant_id")
    if not nonce or not tenant_id:
        raise OAuthStateError("Invalid OAuth state payload")

    # Constant-time comparison of the cookie digest against the HMAC of the
    # decoded nonce, before touching Redis.
    expected_digest = hash_oauth_nonce(str(nonce))
    if not hmac.compare_digest(str(cookie_digest), str(expected_digest)):
        raise OAuthStateError("OAuth session binding cookie mismatch")

    stored_tenant = await pop_oauth_state(str(nonce))
    if stored_tenant is None:
        raise OAuthStateError("OAuth state already used or unknown")

    if not hmac.compare_digest(str(stored_tenant), str(tenant_id)):
        raise OAuthStateError("OAuth state tenant mismatch")

    return str(tenant_id)

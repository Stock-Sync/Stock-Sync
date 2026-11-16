import re
import sys
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRETS = {
    "change_me",
    "secret",
    "password",
    "changeme",
    "your-super-secret-jwt-key-change-in-production",
    "your-internal-service-secret-change-in-production",
}

_WEAK_DB_PASSWORDS = {"postgres", "password", "123456"}


def _is_weak_secret(value: str, name: str) -> bool:
    if value in _WEAK_SECRETS or len(value) < 32:
        print(
            f"FATAL: {name} is weak or too short "
            "(must be >= 32 chars and not a placeholder)"
        )
        return True
    return False


def _has_weak_db_password(url: str) -> bool:
    try:
        parsed = urlparse(url)
        password = parsed.password
        if password and password.lower() in _WEAK_DB_PASSWORDS:
            print("FATAL: DATABASE_URL contains a weak database password")
            return True
    except Exception:
        pass
    return False


class Settings(BaseSettings):
    app_name: str = "StockSync"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_integrations"
    )
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    mercado_livre_app_id: str = ""
    mercado_livre_client_secret: str = ""
    shopee_partner_id: str = ""
    shopee_partner_key: str = ""

    # Public base URL of this API (used for OAuth redirect + webhook callback)
    public_api_url: str = "https://dreamt-roundness-tightwad.ngrok-free.dev"
    frontend_url: str = "http://localhost:5173"
    # Shared secret embedded in the callback URL. Mercado Livre does not sign
    # webhook requests, so this is the only shared-secret mechanism available.
    # Required when DEBUG is false; use URL-safe characters only.
    ml_webhook_secret: str = ""
    # How long a notification id is remembered to short-circuit redeliveries.
    # End-to-end idempotency still lives in sync-service's SyncEvent.dedupe_key.
    ml_webhook_dedup_ttl_seconds: int = 3600
    # Lifetime of the signed OAuth state nonce (spec: 600 s).
    oauth_state_ttl_seconds: int = 600
    # Name of the HttpOnly browser cookie that binds the OAuth state to the
    # initiating browser session (Plan 14).
    oauth_state_cookie_name: str = "ml_oauth_nonce"
    # Distributed lock used while refreshing Mercado Livre tokens. The TTL
    # bounds how long a crashed process can block the tenant; the timeout is
    # how long a competing process waits for the lock holder to finish.
    ml_refresh_lock_ttl_seconds: int = 15
    ml_refresh_lock_timeout_seconds: int = 10
    # Refresh tokens this many seconds before they actually expire so requests
    # never race the expiration boundary (spec: 600 s).
    ml_refresh_buffer_seconds: int = 600
    # Shared secret guarding service-to-service (internal) endpoints
    internal_service_secret: str = "your-internal-service-secret-change-in-production"
    # Base URL of catalog-service, used to create/reactivate the PlatformMapping
    # after an orchestrated listing creation and to unbind it on deletion.
    catalog_service_url: str = "http://localhost:8001"

    # JWT settings (shared with auth-service for token validation)
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"

    # Cloudinary Configuration
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    def validate_production_hardening(self) -> None:
        """Fail-fast validation for production deployments.

        Called during FastAPI lifespan startup. Aborts with ``sys.exit(1)``
        when ``ENVIRONMENT=production`` and any security rule is violated.
        Safe to skip in development (CLI tasks, alembic migrations, etc.).
        """
        if self.environment != "production":
            return

        if self.debug:
            print("FATAL: DEBUG must not be true in production")
            sys.exit(1)

        if _is_weak_secret(self.jwt_secret_key, "JWT_SECRET_KEY"):
            sys.exit(1)

        if _is_weak_secret(self.internal_service_secret, "INTERNAL_SERVICE_SECRET"):
            sys.exit(1)

        if _has_weak_db_password(self.database_url):
            sys.exit(1)

        if not self.ml_webhook_secret:
            print("FATAL: ML_WEBHOOK_SECRET must be set in production")
            sys.exit(1)

        if not self.public_api_url.startswith("https://"):
            print("FATAL: PUBLIC_API_URL must start with https:// in production")
            sys.exit(1)

    @field_validator("ml_webhook_secret")
    @classmethod
    def validate_ml_webhook_secret(cls, value: str) -> str:
        """Keep the secret usable as a single URL path segment.

        The secret travels in the callback URL, so ``/`` (and characters that
        change URL parsing) would silently make the route unreachable.
        """
        if value and not re.fullmatch(r"[A-Za-z0-9._~-]+", value):
            raise ValueError(
                "ML_WEBHOOK_SECRET must use only URL-safe characters "
                "(A-Z, a-z, 0-9, '-', '_', '.', '~')"
            )
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

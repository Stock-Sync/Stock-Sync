import sys
from functools import lru_cache
from urllib.parse import urlparse

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

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_catalog"
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # JWT Settings (must match auth-service so tenant_id can be resolved)
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"

    # Shared secret for internal service-to-service calls (sync-service).
    internal_service_secret: str = "your-internal-service-secret-change-in-production"

    # Used to pause/zero listings and update seller_custom_field before an
    # orchestrated unbind (Plan 9).
    integrations_service_url: str = "http://localhost:8003"

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

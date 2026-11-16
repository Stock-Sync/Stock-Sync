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

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_sync"
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    catalog_service_url: str = "http://localhost:8001"
    integrations_service_url: str = "http://localhost:8003"
    sales_service_url: str = "http://localhost:8004"

    # Shared secret guarding service-to-service endpoints of other services
    internal_service_secret: str = "your-internal-service-secret-change-in-production"

    # JWT settings (shared with auth-service to resolve the tenant from cookies)
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"

    # Background workers
    consumer_enabled: bool = True
    flusher_enabled: bool = True
    flusher_interval_seconds: float = 3.0
    stream_max_attempts: int = 5
    stream_claim_min_idle_ms: int = 30000

    # Stock adjustment claims: the lease must outlive an HTTP adjustment and
    # the heartbeat renews it while the call is in flight.
    claim_lease_seconds: float = 90.0
    claim_heartbeat_seconds: float = 20.0
    dead_letter_replay_limit: int = 100

    # Listings reconciliation safety circuit breaker. A run is flagged instead
    # of soft-deleting when the missing set exceeds this fraction of the local
    # active mirror (protects against truncated searches and network errors).
    sync_safety_threshold_ratio: float = 0.10

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

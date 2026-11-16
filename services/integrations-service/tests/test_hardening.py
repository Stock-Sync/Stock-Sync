"""Plan 13: Production configuration hardening tests for integrations-service.

Covers the fail-fast validation rules enforced by
``Settings.validate_production_hardening()`` during lifespan startup.
"""

import pytest
from app.core.config import Settings


def test_development_mode_allows_debug_and_weak_secrets():
    """Development mode must skip all production hardening checks."""
    settings = Settings(
        environment="development",
        debug=True,
        jwt_secret_key="short",
        internal_service_secret="short",
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_integrations",
        public_api_url="http://localhost:8003",
        ml_webhook_secret="",
    )
    # Should not raise.
    settings.validate_production_hardening()


def test_development_mode_allows_http_public_url():
    """Development mode with HTTP PUBLIC_API_URL starts normally (no SystemExit)."""
    settings = Settings(
        environment="development",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="http://localhost:8003",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    settings.validate_production_hardening()


def test_production_fails_if_debug_is_true():
    """Refuse production startup when DEBUG=True."""
    settings = Settings(
        environment="production",
        debug=True,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_fails_on_weak_jwt_secret():
    """Refuse production when JWT_SECRET_KEY is a placeholder."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="change_me",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_fails_on_short_jwt_secret():
    """Refuse production when JWT_SECRET_KEY is shorter than 32 chars."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="too_short",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_fails_on_weak_internal_secret():
    """Refuse production when INTERNAL_SERVICE_SECRET is a placeholder."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="your-internal-service-secret-change-in-production",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_fails_on_weak_db_password():
    """Refuse production when DATABASE_URL contains a weak database password."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_integrations_fails_on_http_public_url():
    """Refuse production when PUBLIC_API_URL does not start with https://."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="http://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_integrations_fails_on_empty_ml_webhook_secret():
    """Refuse production when ML_WEBHOOK_SECRET is empty."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="",
    )
    with pytest.raises(SystemExit):
        settings.validate_production_hardening()


def test_production_passes_with_all_secure_settings():
    """Production startup succeeds when all hardening rules are satisfied."""
    settings = Settings(
        environment="production",
        debug=False,
        jwt_secret_key="a_very_secure_and_long_random_jwt_secret_key_for_prod",
        internal_service_secret="another_very_secure_internal_service_secret_key",
        database_url="postgresql+psycopg://postgres:strong_password@localhost:5432/stocksync_integrations",
        public_api_url="https://api.mysynchub.com",
        ml_webhook_secret="valid_webhook_secret_key",
    )
    settings.validate_production_hardening()

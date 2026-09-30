from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────
    app_name: str = "integrations-service"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = (
        (
        "postgresql+psycopg://postgres:postgres@localhost:5432/stocksync_integrations"
    )
    )
    db_echo: bool = False

    # ── Cache ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────────────────────
    # Chave Fernet base64 — gere com: Fernet.generate_key().decode()
    encryption_key: str = ""

    # ── Mercado Livre ─────────────────────────────────────────────────────
    ml_app_id: str = ""
    ml_client_secret: str = ""
    ml_redirect_uri: str = (
        "http://localhost:5173/integrations/mercadolivre/callback"
    )
    ml_api_base_url: str = "https://api.mercadolibre.com"

    # ── Shopee ────────────────────────────────────────────────────────────
    shopee_partner_id: str = ""
    shopee_partner_key: str = ""
    shopee_redirect_uri: str = (
        "http://localhost:5173/integrations/shopee/callback"
    )
    shopee_api_base_url: str = "https://partner.shopeemobile.com"

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

from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class Marketplace(str, Enum):
    mercadolivre = "mercado_livre"
    shopee = "shopee"


class MarketplaceCredential(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    marketplace: Marketplace = Field(index=True)
    account_name: str = Field(min_length=1, max_length=120)
    access_token: str = Field(min_length=1, max_length=2000)
    refresh_token: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

from datetime import datetime

from pydantic import field_serializer
from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.marketplace_credential import Marketplace


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}***{token[-4:]}"


class MarketplaceCredentialCreate(SQLModel):
    marketplace: Marketplace
    account_name: str = Field(min_length=1, max_length=120)
    access_token: str = Field(min_length=1, max_length=2000)
    refresh_token: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = Field(default=None)


class MarketplaceCredentialUpdate(SQLModel):
    account_name: str | None = Field(default=None, min_length=1, max_length=120)
    access_token: str | None = Field(default=None, min_length=1, max_length=2000)
    refresh_token: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class MarketplaceCredentialRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    marketplace: Marketplace
    account_name: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("access_token")
    def mask_access_token(self, value: str) -> str:
        return mask_token(value) or ""

    @field_serializer("refresh_token")
    def mask_refresh_token(self, value: str | None) -> str | None:
        return mask_token(value)

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel, Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid6 import uuid7


class TenantIntegration(SQLModel, table=True):
    """Armazena as credenciais OAuth de cada integração por tenant (usuário do SaaS)."""

    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", "external_seller_id",
            name="uq_tenant_integration_user_platform_seller"
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    # ID do tenant/usuário no SaaS (vem do auth-service via JWT)
    user_id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), index=True, nullable=False),
    )
    # 'mercadolivre' ou 'shopee'
    platform: str = Field(max_length=30, nullable=False, index=True)
    # seller_id (ML) ou shop_id (Shopee) — identificador do vendedor no marketplace
    external_seller_id: str = Field(max_length=100, index=True, nullable=False)

    # Tokens armazenados criptografados em repouso via Fernet
    access_token_encrypted: str = Field(sa_column=Column("access_token_encrypted", nullable=False))
    refresh_token_encrypted: str = Field(sa_column=Column("refresh_token_encrypted", nullable=False))

    access_token_expires_at: datetime = Field(sa_column=Column("access_token_expires_at", nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

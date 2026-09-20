import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TenantIntegration(Base):
    """Armazena as credenciais OAuth de cada integração por tenant (usuário do SaaS)."""

    __tablename__ = "tenant_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # ID do tenant/usuário no SaaS (vem do auth-service via JWT)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    # 'mercadolivre' ou 'shopee'
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    # seller_id (ML) ou shop_id (Shopee) — identificador do vendedor no marketplace
    external_seller_id: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )

    # Tokens armazenados criptografados em repouso via Fernet
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

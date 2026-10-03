"""
Modelos SQLModel para o sync-service.

Persiste estado de sincronização, logs de auditoria e deduplicação.
"""

import uuid
from datetime import UTC, datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Column, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid6 import uuid7


class SyncAuditLog(SQLModel, table=True):
    """
    Log de auditoria de sincronização para rastreamento e debugging.
    """

    __tablename__ = "sync_audit_logs"

    id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    user_id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), index=True),
        description="ID do tenant no SaaS",
    )
    platform: str = Field(index=True, description="mercadolivre ou shopee")
    event_type: str = Field(description="Tipo do evento original: order.created, etc.")
    order_id: Optional[str] = Field(default=None, index=True)
    item_id: Optional[str] = Field(default=None, index=True)
    sku: Optional[str] = Field(default=None, index=True)
    old_quantity: Optional[int] = Field(default=None)
    new_quantity: Optional[int] = Field(default=None)
    status: str = Field(
        default="pending",
        description="pending, published, failed, completed",
    )
    error_message: Optional[str] = Field(default=None)
    original_event_id: str = Field(description="ID do evento no marketplaces:events")
    metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    completed_at: Optional[datetime] = Field(default=None)


class SyncState(SQLModel, table=True):
    """
    Estado de sincronização por SKU/tenant para controle de concorrência
    e prevenção de race conditions.
    """

    __tablename__ = "sync_states"

    id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    user_id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), index=True),
    )
    platform: str = Field(index=True)
    sku: str = Field(index=True)
    item_id: str = Field(index=True)
    model_id: int = Field(default=0)
    current_quantity: int = Field(default=0)
    pending_quantity: Optional[int] = Field(default=None)
    last_event_id: Optional[str] = Field(default=None)
    last_event_type: Optional[str] = Field(default=None)
    locked: bool = Field(default=False, description="Lock para prevenir concorrência")
    locked_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IdempotencyKey(SQLModel, table=True):
    """
    Chaves de idempotência persistidas para deduplicação robusta
    (além do Redis, para sobrevivência a restarts).
    """

    __tablename__ = "idempotency_keys"

    key: str = Field(primary_key=True, max_length=255)
    event_id: str = Field(index=True)
    user_id: uuid.UUID = Field(
        default_factory=uuid7,
        sa_column=Column(PG_UUID(as_uuid=True), index=True),
    )
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(index=True)
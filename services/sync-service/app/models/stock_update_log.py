from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class StockUpdateLog(SQLModel, table=True):
    """Audit trail of stock changes, also used as an idempotency claim.

    A marketplace sale writes a row with ``source_platform="ml_sale"`` before
    touching the catalog; the unique constraint makes a redelivered order
    notification a no-op. A cancellation writes ``ml_cancellation`` for the
    same (order, item) pair, so it can only be reversed once.

    Claim states:
    - ``in_progress``: a worker owns the movement until ``lease_expires_at``;
      ``heartbeat_at`` is renewed while the external call is running.
    - ``applied``: the catalog accepted the movement. Terminal.
    - ``failed``: the external call failed and can be retried. Terminal for
      cancellations that never had a deduction is ``skipped`` instead.
    - ``skipped``: nothing had to move (for example, a cancellation arrived
      before any stock was deducted). Terminal tombstone.
    """

    __table_args__ = (
        UniqueConstraint(
            "marketplace_order_id",
            "marketplace_item_id",
            "source_platform",
            name="uq_order_item_stock_adjust",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    internal_sku: str = Field(index=True, min_length=1, max_length=50)
    previous_quantity: int = Field(ge=0)
    new_quantity: int = Field(ge=0)
    source_platform: str = Field(max_length=50)
    # Marketplace identifiers used by the idempotency constraint. NULL for
    # changes that did not originate from a marketplace order.
    marketplace_order_id: str | None = Field(default=None, index=True, max_length=100)
    marketplace_item_id: str | None = Field(default=None, max_length=100)
    status: str = Field(default="in_progress", index=True, max_length=20)
    # Quantity that was actually removed from stock (sales only). A clamped
    # sale may deduct less than the ordered quantity, so cancellations return
    # exactly this amount instead of the marketplace quantity.
    deducted_quantity: int = Field(default=0, ge=0)
    clamped: bool = Field(default=False)
    attempts: int = Field(default=0, ge=0)
    lease_expires_at: datetime | None = Field(default=None)
    heartbeat_at: datetime | None = Field(default=None)
    error_message: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

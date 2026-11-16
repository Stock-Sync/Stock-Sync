"""Plan 11 rules for the Product 1:1 SKU relationship.

Both the composite endpoints and the legacy ``/skus`` endpoints call these
helpers so the same invariants are enforced regardless of the client:

* at most one active SKU per product;
* at most one active ``internal_sku`` per tenant;
* ``internal_sku`` is immutable while a non-deleted marketplace mapping exists.
"""

from sqlmodel import Session, select

from app.core.errors import APIError, ConflictError
from app.models import PlatformMapping, SKU

INTERNAL_SKU_LOCKED = "internal_sku_locked"
INTERNAL_SKU_LOCKED_MESSAGE = (
    "Não é possível alterar o código SKU de um produto com anúncios ativos "
    "vinculados."
)


def ensure_sku_uniqueness(
    session: Session,
    *,
    tenant_id: str,
    product_id: int | None = None,
    internal_sku: str | None,
    exclude_sku_id: int | None = None,
) -> None:
    """Raise ``409`` when the tenant code or the product 1:1 rule is violated."""
    if internal_sku is not None:
        # Tenant-scoped so the same code stays valid in another tenant; the
        # ``is_deleted`` filter allows reusing an archived code.
        statement = select(SKU.id).where(
            SKU.tenant_id == tenant_id,
            SKU.internal_sku == internal_sku,
            SKU.is_deleted.is_(False),
        )
        if exclude_sku_id is not None:
            statement = statement.where(SKU.id != exclude_sku_id)
        if session.exec(statement).first() is not None:
            raise ConflictError(
                "Já existe um SKU ativo com este código neste tenant."
            )

    statement = select(SKU.id).where(
        SKU.product_id == product_id,
        SKU.is_deleted.is_(False),
    )
    if exclude_sku_id is not None:
        statement = statement.where(SKU.id != exclude_sku_id)
    if product_id is not None and session.exec(statement).first() is not None:
        raise ConflictError("O produto já possui um SKU ativo.")


def ensure_internal_sku_editable(
    session: Session,
    *,
    sku_id: int,
    tenant_id: str,
    current_internal_sku: str,
    new_internal_sku: str | None,
) -> None:
    """Lock the SKU code when a non-deleted marketplace mapping exists.

    Paused or inactive mappings still point at the external listing and use the
    code for reconciliation, so only a soft-deleted mapping allows the edit.
    """
    if new_internal_sku is None or new_internal_sku == current_internal_sku:
        return

    mapping_id = session.exec(
        select(PlatformMapping.id).where(
            PlatformMapping.sku_id == sku_id,
            PlatformMapping.tenant_id == tenant_id,
            PlatformMapping.is_deleted.is_(False),
        )
    ).first()
    if mapping_id is not None:
        raise APIError(
            status_code=400,
            code=INTERNAL_SKU_LOCKED,
            message=INTERNAL_SKU_LOCKED_MESSAGE,
        )

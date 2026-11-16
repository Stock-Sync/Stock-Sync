import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.deps import get_tenant_id
from app.core.errors import APIError, NotFoundError
from app.core.redis import publish_stock_adjust
from app.db.session import get_session
from app.models import SKU, Platform, PlatformMapping, Product
from app.schemas import (
    ProductCompositeCreate,
    ProductCompositeRead,
    ProductCompositeUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    SKURead,
)
from app.services import integrations_client
from app.services.sku_rules import (
    ensure_internal_sku_editable,
    ensure_sku_uniqueness,
)

logger = logging.getLogger(__name__)

router = APIRouter()
# Mounted by ``app.main`` under ``/api/v1/internal/products``.
internal_router = APIRouter()

PRODUCT_HAS_ACTIVE_LISTINGS = "product_has_active_listings"
PRODUCT_DELETED_REASON = "product_deleted"


def _get_product_or_404(
    session: Session,
    product_id: int,
    tenant_id: str,
    include_deleted: bool = False,
) -> Product:
    product = session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise NotFoundError("Product")
    if not include_deleted and product.is_deleted:
        raise NotFoundError("Product")
    return product


def _get_product_skus(session: Session, product_id: int, tenant_id: str) -> list[SKU]:
    return list(
        session.exec(
            select(SKU).where(
                SKU.product_id == product_id,
                SKU.tenant_id == tenant_id,
            )
        ).all()
    )


def _get_active_product_sku_or_404(
    session: Session, product_id: int, tenant_id: str
) -> SKU:
    """Return the single active SKU of a product (Plan 11 1:1 contract)."""
    sku = session.exec(
        select(SKU)
        .where(
            SKU.product_id == product_id,
            SKU.tenant_id == tenant_id,
            SKU.is_deleted.is_(False),
        )
        .order_by(SKU.id.desc())
    ).first()
    if sku is None:
        raise NotFoundError("SKU")
    return sku


def _has_active_listing(session: Session, product_id: int, tenant_id: str) -> bool:
    """Check if a product has at least one active marketplace listing (Plan 12).

    Used for UI read-only state and for enforcing that ML-managed fields cannot
    be edited when a listing is active.
    """
    mapping = session.exec(
        select(PlatformMapping)
        .join(SKU, SKU.id == PlatformMapping.sku_id)
        .where(
            SKU.product_id == product_id,
            SKU.tenant_id == tenant_id,
            PlatformMapping.tenant_id == tenant_id,
            PlatformMapping.is_deleted.is_(False),
            PlatformMapping.is_active.is_(True),
        )
    ).first()
    return mapping is not None


def _composite_read(
    product: Product,
    sku: SKU,
    session: Session | None = None,
    tenant_id: str | None = None,
) -> ProductCompositeRead:
    """Build ProductCompositeRead with dynamically computed ``has_active_listing``."""
    sku_read = SKURead.model_validate(sku)
    has_active_listing = False
    if session is not None and tenant_id is not None:
        has_active_listing = _has_active_listing(session, product.id, tenant_id)
    return ProductCompositeRead(
        id=product.id,
        tenant_id=product.tenant_id,
        name=product.name,
        description=product.description,
        is_description_truncated=getattr(product, "is_description_truncated", False),
        pictures=product.pictures,
        is_deleted=product.is_deleted,
        created_at=product.created_at,
        updated_at=product.updated_at,
        has_active_listing=has_active_listing,
        sku=sku_read,
    )


def _should_update_product_from_ml(
    product: Product, ml_updated_at: datetime, source: str
) -> bool:
    """Determine whether to update product metadata from Mercado Livre.

    Returns True only if the ML notification is newer than our current record.
    This prevents race conditions where older events overwrite newer local
    changes. ``source`` is used for audit logging.
    """
    if not product.updated_at:
        return True
    # Compare naive datetimes; ML timestamps should be UTC.
    if ml_updated_at > product.updated_at:
        logger.debug(
            "sync_from_ml",
            extra={
                "product_id": product.id,
                "source": source,
                "ml_updated_at": ml_updated_at.isoformat(),
                "local_updated_at": product.updated_at.isoformat(),
            },
        )
        return True
    logger.debug(
        "skip_sync_from_ml",
        extra={
            "product_id": product.id,
            "source": source,
            "ml_updated_at": ml_updated_at.isoformat(),
            "local_updated_at": product.updated_at.isoformat(),
        },
    )
    return False


def _truncate_description(text: str | None, max_length: int = 2000) -> tuple[str | None, bool]:
    """Truncate description and return (truncated_text, is_truncated)."""
    if not text:
        return None, False
    is_truncated = len(text) > max_length
    return (text[:max_length], is_truncated) if is_truncated else (text, False)


def _mapping_blocks_deletion(
    mapping: PlatformMapping, detail: dict | None
) -> bool:
    """Return True when a non-deleted mapping still points at an active listing.

    ``status`` from the integrations mirror is authoritative when present
    (Plan 10): ``paused``/``closed`` listings already stopped selling and can
    be archived, while ``active`` listings must be paused or unlinked first.
    Unknown/missing status falls back to the mapping lifecycle flag.
    """
    if mapping.is_deleted or not mapping.platform_product_id:
        return False

    if detail is not None:
        if detail.get("is_deleted"):
            return False
        status = detail.get("status")
        if status == "active":
            return True
        if status in {"paused", "closed"}:
            return False

    return bool(mapping.is_active)


async def _fetch_listing_details(
    tenant_id: str, mappings: list[PlatformMapping]
) -> dict[str, dict]:
    """Best-effort enrichment of ML listing status/permalink for the 409 body.

    An integrations outage must not hide the existence of active local links:
    the caller falls back to the mapping lifecycle flags and still returns a
    structured 409 so the UI can retry.
    """
    item_ids = [
        mapping.platform_product_id
        for mapping in mappings
        if mapping.platform == Platform.mercadolivre and mapping.platform_product_id
    ]
    if not item_ids:
        return {}
    try:
        details = await integrations_client.batch_item_details(
            tenant_id, list(dict.fromkeys(item_ids))
        )
    except APIError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "listing_details_unexpected_error",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        return {}
    return {detail.get("id"): detail for detail in details if detail.get("id")}


@router.get("", response_model=list[ProductRead])
def list_products(
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> list[ProductRead]:
    statement = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.is_deleted.is_(False),
    )
    products = list(session.exec(statement).all())
    if not products:
        return []
    # Plan 12: compute has_active_listing for each product.
    product_ids = [p.id for p in products if p.id is not None]
    active_mapping_products = set(
        session.exec(
            select(SKU.product_id)
            .join(PlatformMapping, PlatformMapping.sku_id == SKU.id)
            .where(
                SKU.product_id.in_(product_ids),
                SKU.tenant_id == tenant_id,
                PlatformMapping.tenant_id == tenant_id,
                PlatformMapping.is_deleted.is_(False),
                PlatformMapping.is_active.is_(True),
            )
            .distinct()
        ).all()
    )
    result = []
    for p in products:
        result.append(
            ProductRead.model_validate(
                p,
                update={
                    "has_active_listing": p.id in active_mapping_products,
                },
            )
        )
    return result


@router.post("", response_model=ProductRead, status_code=201)
def create_product(
    payload: ProductCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    product = Product(**payload.model_dump(), tenant_id=tenant_id)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.post("/composite", response_model=ProductCompositeRead, status_code=201)
def create_product_composite(
    payload: ProductCompositeCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> ProductCompositeRead:
    """Create a Product and its single SKU in one transaction (Plan 11).

    ``session.commit()`` is the only commit point. Any validation or database
    failure rolls both rows back, so a failed SKU never leaves an orphan
    product behind.
    """
    ensure_sku_uniqueness(
        session,
        tenant_id=tenant_id,
        internal_sku=payload.internal_sku,
    )
    now = datetime.now(UTC)
    product = Product(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        pictures=list(payload.pictures),
        created_at=now,
        updated_at=now,
    )

    try:
        session.add(product)
        # Flush to obtain product.id without ending the transaction.
        session.flush()
        sku = SKU(
            tenant_id=tenant_id,
            product_id=product.id,
            internal_sku=payload.internal_sku,
            price=float(payload.price),
            stock_quantity=payload.stock_quantity,
            created_at=now,
            updated_at=now,
        )
        session.add(sku)
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(product)
    session.refresh(sku)
    if sku.stock_quantity:
        publish_stock_adjust(
            sku.id,
            sku.internal_sku,
            0,
            sku.stock_quantity,
            "product_create",
            tenant_id=tenant_id,
        )
    return _composite_read(product, sku, session=session, tenant_id=tenant_id)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    return _get_product_or_404(session, product_id, tenant_id)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    product = _get_product_or_404(session, product_id, tenant_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    # Plan 10: every catalog mutation refreshes updated_at so stale-event
    # protection and the listings UI can order changes correctly.
    product.updated_at = datetime.now(UTC)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.put("/{product_id}/composite", response_model=ProductCompositeRead)
def update_product_composite(
    product_id: int,
    payload: ProductCompositeUpdate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> ProductCompositeRead:
    """Update a Product and its single SKU atomically (Plan 11).

    The SKU code is immutable while any non-deleted marketplace mapping exists;
    all other catalog fields remain editable.
    """
    product = _get_product_or_404(session, product_id, tenant_id)
    sku = _get_active_product_sku_or_404(session, product_id, tenant_id)
    data = payload.model_dump(exclude_unset=True)

    new_internal_sku = data.get("internal_sku")
    ensure_internal_sku_editable(
        session,
        sku_id=sku.id,
        tenant_id=tenant_id,
        current_internal_sku=sku.internal_sku,
        new_internal_sku=new_internal_sku,
    )
    ensure_sku_uniqueness(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        internal_sku=(
            new_internal_sku
            if new_internal_sku is not None
            else sku.internal_sku
        ),
        exclude_sku_id=sku.id,
    )

    # Plan 12: when a product has an active listing, ML-managed fields
    # (name, description, pictures, price) are read-only via composite PUT.
    has_active = _has_active_listing(session, product_id, tenant_id)
    if has_active:
        ml_managed_fields = {"name", "description", "pictures", "price"}
        attempted_ml = ml_managed_fields & set(data.keys())
        if attempted_ml:
            raise APIError(
                status_code=400,
                code="ml_managed_field_readonly",
                message=(
                    f"Cannot edit {', '.join(sorted(attempted_ml))} while the "
                    "product has an active listing on Mercado Livre. These "
                    "fields are managed via the Mercado Livre dashboard."
                ),
                details={
                    "readonly_fields": sorted(attempted_ml),
                    "editable_fields": ["stock_quantity"],
                },
            )

    previous_quantity = sku.stock_quantity
    now = datetime.now(UTC)

    for field in ("name", "description", "pictures"):
        if field in data:
            setattr(product, field, data[field])
    product.updated_at = now
    if "internal_sku" in data and data["internal_sku"] is not None:
        sku.internal_sku = data["internal_sku"]
    if "price" in data and data["price"] is not None:
        sku.price = float(data["price"])
    if "stock_quantity" in data and data["stock_quantity"] is not None:
        sku.stock_quantity = data["stock_quantity"]
    sku.updated_at = now

    try:
        session.add(product)
        session.add(sku)
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(product)
    session.refresh(sku)
    if sku.stock_quantity != previous_quantity:
        publish_stock_adjust(
            sku.id,
            sku.internal_sku,
            previous_quantity,
            sku.stock_quantity,
            "catalog_update",
            tenant_id=tenant_id,
        )
    return _composite_read(product, sku, session=session, tenant_id=tenant_id)


@router.post("/{product_id}/unbind-listings", response_model=dict)
def unbind_product_listings(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> dict:
    """Remove all local marketplace links of a product being deleted.

    Used by the deletion resolution dialog ("Desvincular"). It only mutates
    local state: pausing/zeroing the remote listing is a separate, explicit
    action, so a partial network failure never leaves a half-unlinked catalog.
    """
    _get_product_or_404(session, product_id, tenant_id)
    skus = _get_product_skus(session, product_id, tenant_id)
    sku_ids = [sku.id for sku in skus if sku.id is not None]
    if not sku_ids:
        return {"unbound": 0, "platform_product_ids": []}

    mappings = list(
        session.exec(
            select(PlatformMapping).where(
                PlatformMapping.sku_id.in_(sku_ids),
                PlatformMapping.tenant_id == tenant_id,
                PlatformMapping.is_deleted.is_(False),
            )
        ).all()
    )
    now = datetime.now(UTC)
    platform_product_ids: list[str] = []
    for mapping in mappings:
        mapping.is_deleted = True
        mapping.is_active = False
        mapping.deleted_reason = PRODUCT_DELETED_REASON
        mapping.updated_at = now
        session.add(mapping)
        if mapping.platform_product_id:
            platform_product_ids.append(mapping.platform_product_id)

    if mappings:
        session.commit()
    return {
        "unbound": len(mappings),
        "platform_product_ids": platform_product_ids,
    }


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> None:
    """Soft delete the product, its SKUs and their marketplace mappings.

    Active marketplace listings block the deletion with a structured ``409``
    (Plan 10). Paused/closed listings are allowed because they already stopped
    selling; they are only deactivated locally. The UI resolves the conflict by
    pausing/zeroing and/or unlinking the listings before retrying.
    """
    now = datetime.now(UTC)
    product = _get_product_or_404(session, product_id, tenant_id)

    skus = _get_product_skus(session, product_id, tenant_id)
    sku_ids = [sku.id for sku in skus if sku.id is not None]

    mappings: list[PlatformMapping] = []
    if sku_ids:
        mappings = list(
            session.exec(
                select(PlatformMapping).where(
                    PlatformMapping.sku_id.in_(sku_ids),
                    PlatformMapping.tenant_id == tenant_id,
                    PlatformMapping.is_deleted.is_(False),
                )
            ).all()
        )

    details = await _fetch_listing_details(tenant_id, mappings)
    blocking_listings: list[dict] = []
    seen_item_ids: set[str] = set()
    for mapping in mappings:
        detail = details.get(mapping.platform_product_id or "")
        if not _mapping_blocks_deletion(mapping, detail):
            continue
        item_id = mapping.platform_product_id or ""
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        blocking_listings.append(
            {
                "id": item_id,
                "status": detail.get("status") if detail else None,
                "permalink": detail.get("permalink") if detail else None,
            }
        )

    if blocking_listings:
        raise APIError(
            status_code=409,
            code=PRODUCT_HAS_ACTIVE_LISTINGS,
            message=(
                "Não é possível excluir um produto com anúncios ativos "
                "vinculados."
            ),
            details={
                "product_id": product_id,
                "product_name": product.name,
                "listings": blocking_listings,
            },
        )

    product.is_deleted = True
    product.updated_at = now
    session.add(product)

    for sku in skus:
        sku.is_deleted = True
        sku.updated_at = now
        session.add(sku)

    for mapping in mappings:
        mapping.is_active = False
        mapping.updated_at = now
        session.add(mapping)

    session.commit()


# =============================================================================
# Internal (service-to-service) endpoints
# =============================================================================


@internal_router.put("/{product_id}/metadata-from-ml", response_model=dict)
def mirror_product_metadata_from_ml(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
    name: str | None = None,
    description: str | None = None,
    pictures: list[str] | None = None,
    is_description_truncated: bool | None = None,
) -> dict:
    """Mirror Mercado Livre metadata into the catalog Product (internal call).

    Bypasses the read-only enforcement of ``PUT /products/{id}`` because this
    is a server-to-server sync, not a user edit. Only ML-managed fields are
    touched: name, description, pictures, is_description_truncated.
    ``stock_quantity`` and ``internal_sku`` are never overwritten here.
    """
    product = _get_product_or_404(session, product_id, tenant_id)

    ml_updated_at = datetime.now(UTC)
    if not _should_update_product_from_ml(product, ml_updated_at, "items_changed"):
        return {"updated": False, "reason": "stale_event"}

    updated = False
    if name is not None:
        product.name = name
        updated = True
    if description is not None:
        truncated_text, was_truncated = _truncate_description(description)
        product.description = truncated_text
        if is_description_truncated is not None:
            product.is_description_truncated = is_description_truncated
        elif was_truncated:
            product.is_description_truncated = True
        updated = True
    if pictures is not None:
        product.pictures = list(pictures)
        updated = True
    if is_description_truncated is not None and description is None:
        product.is_description_truncated = is_description_truncated
        updated = True

    if updated:
        product.updated_at = ml_updated_at
        session.add(product)
        session.commit()
        session.refresh(product)

    return {"updated": updated, "product_id": product_id}

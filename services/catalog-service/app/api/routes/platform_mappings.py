from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.deps import get_internal_tenant_id, get_tenant_id
from app.core.errors import APIError, ConflictError, NotFoundError
from app.core.redis import publish_stock_adjust
from app.db.session import get_session
from app.models import SKU, Platform, PlatformMapping, Product
from app.schemas import (
    PlatformMappingCreate,
    PlatformMappingInternalCreate,
    PlatformMappingRead,
    PlatformMappingRelink,
    PlatformMappingRelinkResponse,
    PlatformMappingSoftDelete,
    PlatformMappingStateUpdate,
    PlatformMappingUnbind,
    PlatformMappingWarning,
)
from app.services import integrations_client

router = APIRouter()
# Mounted by ``app.main`` under ``/api/v1/internal/platform-mappings``.
internal_router = APIRouter()

DELETED_REASON_USER = "user"
DELETED_REASON_RECONCILE = "reconcile"
DELETED_REASON_PRODUCT_DELETED = "product_deleted"
DELETED_REASON_LISTING_DELETED = "listing_deleted"

# Reasons that mean "the listing simply disappeared"; if it reappears the link
# can be recreated automatically. User deletions are never resurrected.
RECONCILABLE_REASONS = {
    DELETED_REASON_RECONCILE,
    DELETED_REASON_LISTING_DELETED,
    # Plan 8 uses this more specific reason for reconciled listings.
    "reconciliation_missing",
}


def _get_mapping_or_404(
    session: Session,
    mapping_id: int,
    tenant_id: str,
    include_deleted: bool = False,
) -> PlatformMapping:
    mapping = session.get(PlatformMapping, mapping_id)
    if mapping is None or mapping.tenant_id != tenant_id:
        raise NotFoundError("PlatformMapping")
    if mapping.is_deleted and not include_deleted:
        raise NotFoundError("PlatformMapping")
    return mapping


def _find_mapping_for_listing(
    session: Session,
    tenant_id: str,
    platform: Platform,
    platform_product_id: str,
) -> PlatformMapping | None:
    """Return the newest mapping for a listing, including soft-deleted rows."""
    return session.exec(
        select(PlatformMapping)
        .where(
            PlatformMapping.tenant_id == tenant_id,
            PlatformMapping.platform == platform,
            PlatformMapping.platform_product_id == platform_product_id,
        )
        # Prefer an active row over an older tombstone, then newest first.
        .order_by(PlatformMapping.is_deleted.asc(), PlatformMapping.id.desc())
    ).first()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _publish_reactivation_stock(
    sku: SKU, source: str = "listing_reactivated"
) -> None:
    """Push the current local stock once when a listing becomes active again.

    Plan 10: the flusher skips paused/inactive mappings, so the transition
    ``is_active=False -> True`` must seed a fresh ``stock_adjust`` event with
    the current SKU balance. Publishing is best-effort (Redis outage never
    fails the linking request).
    """
    quantity = int(sku.stock_quantity or 0)
    publish_stock_adjust(
        int(sku.id),
        sku.internal_sku,
        quantity,
        quantity,
        source,
        tenant_id=sku.tenant_id,
    )


@router.get("", response_model=list[PlatformMappingRead])
def list_platform_mappings(
    platform: Platform | None = None,
    platform_sku: str | None = Query(default=None, max_length=100),
    platform_product_id: str | None = Query(default=None, max_length=100),
    include_deleted: bool = Query(default=False),
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> list[PlatformMapping]:
    """List active mappings for the current tenant, optionally filtered.

    Soft-deleted mappings are hidden by default; pass ``include_deleted=true``
    only for audits/history.
    """
    statement = select(PlatformMapping).where(PlatformMapping.tenant_id == tenant_id)
    if not include_deleted:
        statement = statement.where(PlatformMapping.is_deleted.is_(False))
    if platform is not None:
        statement = statement.where(PlatformMapping.platform == platform)
    if platform_sku is not None:
        statement = statement.where(PlatformMapping.platform_sku == platform_sku)
    if platform_product_id is not None:
        statement = statement.where(
            PlatformMapping.platform_product_id == platform_product_id
        )
    # Active/newest rows first: callers resolving a listing (including the
    # stock flusher with include_deleted=true) must never pick an old tombstone.
    statement = statement.order_by(
        PlatformMapping.is_deleted.asc(), PlatformMapping.id.desc()
    )
    return list(session.exec(statement).all())


@router.post("/soft-delete", response_model=dict)
def soft_delete_platform_mappings(
    payload: PlatformMappingSoftDelete,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> dict:
    """Soft delete mappings whose marketplace listing no longer exists.

    Called by sync-service after a listings pull: the rows are kept for
    historical sales/audit, but hidden from the catalog and listings UI.
    """
    if not payload.platform_product_ids:
        return {"deleted": 0}

    statement = select(PlatformMapping).where(
        PlatformMapping.tenant_id == tenant_id,
        PlatformMapping.platform == payload.platform,
        PlatformMapping.platform_product_id.in_(payload.platform_product_ids),
        PlatformMapping.is_deleted.is_(False),
    )
    mappings = list(session.exec(statement).all())
    now = datetime.now(UTC)
    for mapping in mappings:
        mapping.is_deleted = True
        mapping.is_active = False
        mapping.deleted_reason = DELETED_REASON_RECONCILE
        mapping.updated_at = now
        session.add(mapping)
    session.commit()
    return {"deleted": len(mappings)}


def _validate_sku_for_tenant(
    session: Session, sku_id: int, tenant_id: str
) -> SKU:
    sku = session.get(SKU, sku_id)
    product = session.get(Product, sku.product_id) if sku is not None else None
    if (
        sku is None
        or sku.tenant_id != tenant_id
        or sku.is_deleted
        or product is None
        or product.is_deleted
    ):
        raise NotFoundError("SKU")
    return sku


def _ensure_mapping(
    session: Session,
    tenant_id: str,
    *,
    sku: SKU,
    platform: Platform,
    platform_sku: str,
    platform_product_id: str,
    platform_variant_id: str | None,
    allow_user_recovery: bool = False,
) -> PlatformMapping:
    """Create/reactivate the active mapping of a listing.

    Resolution matrix (Plan 9):
    - no row: create one;
    - soft-deleted by ``user``: never resurrect automatically (409);
    - soft-deleted by reconciliation/listing deletion: reactivate;
    - soft-deleted because the product was deleted: reactivate only when the
      SKU/product is active again (``_validate_sku_for_tenant`` already ran);
    - anything else (variation, deleted SKU, ...): keep unmapped.
    """
    now = datetime.now(UTC)
    mapping = _find_mapping_for_listing(
        session, tenant_id, platform, platform_product_id
    )
    was_active = bool(mapping is not None and mapping.is_active and not mapping.is_deleted)

    if mapping is not None:
        if mapping.is_deleted:
            reason = mapping.deleted_reason
            if reason == DELETED_REASON_USER and not allow_user_recovery:
                raise APIError(
                    status_code=409,
                    code="mapping_user_deleted",
                    message=(
                        "O vinculo foi removido pelo usuario e exige "
                        "revínculo manual."
                    ),
                    details={
                        "platform_product_id": platform_product_id,
                        "sku_id": sku.id,
                    },
                )
            if (
                not allow_user_recovery
                and reason not in RECONCILABLE_REASONS
                and reason != DELETED_REASON_PRODUCT_DELETED
            ):
                raise APIError(
                    status_code=409,
                    code="mapping_not_reactivatable",
                    message="Este anuncio nao pode ser revinculado automaticamente.",
                    details={
                        "platform_product_id": platform_product_id,
                        "deleted_reason": reason,
                    },
                )

        mapping.sku_id = int(sku.id)
        mapping.platform_sku = platform_sku
        mapping.platform_variant_id = platform_variant_id
        mapping.is_active = True
        mapping.is_deleted = False
        mapping.deleted_reason = None
        mapping.updated_at = now
        session.add(mapping)
        session.commit()
        session.refresh(mapping)
        if not was_active:
            _publish_reactivation_stock(sku)
        return mapping

    # Same SKU/platform_sku can only have one active mapping. Check eagerly so
    # callers receive a clear 409 instead of a database IntegrityError.
    conflicting = session.exec(
        select(PlatformMapping).where(
            PlatformMapping.tenant_id == tenant_id,
            PlatformMapping.sku_id == sku.id,
            PlatformMapping.platform == platform,
            PlatformMapping.platform_sku == platform_sku,
            PlatformMapping.is_deleted.is_(False),
        )
    ).first()
    if conflicting is not None:
        raise ConflictError("SKU ja possui um vinculo ativo nesta plataforma.")

    mapping = PlatformMapping(
        tenant_id=tenant_id,
        sku_id=int(sku.id),
        platform=platform,
        platform_sku=platform_sku,
        platform_product_id=platform_product_id,
        platform_variant_id=platform_variant_id,
        is_active=True,
    )
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


@router.post("", response_model=PlatformMappingRead, status_code=201)
def create_platform_mapping(
    payload: PlatformMappingCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> PlatformMapping:
    sku = _validate_sku_for_tenant(session, payload.sku_id, tenant_id)
    if not payload.platform_product_id:
        mapping = PlatformMapping(**payload.model_dump(), tenant_id=tenant_id)
        session.add(mapping)
        session.commit()
        session.refresh(mapping)
        return mapping
    return _ensure_mapping(
        session,
        tenant_id,
        sku=sku,
        platform=payload.platform,
        platform_sku=payload.platform_sku,
        platform_product_id=payload.platform_product_id,
        platform_variant_id=payload.platform_variant_id,
    )


@router.post("/re-link", response_model=PlatformMappingRelinkResponse)
async def relink_platform_mapping(
    payload: PlatformMappingRelink,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> PlatformMappingRelinkResponse:
    """Manually link a listing to a SKU (controlled re-link).

    The local mapping is created/updated first. Updating the ML
    ``seller_custom_field`` is best-effort: some categories reject it, and the
    local link by ``item_id`` remains valid, so the response carries a
    non-blocking warning instead of failing.
    """
    sku = _validate_sku_for_tenant(session, payload.sku_id, tenant_id)

    other_active = session.exec(
        select(PlatformMapping).where(
            PlatformMapping.tenant_id == tenant_id,
            PlatformMapping.platform == payload.platform,
            PlatformMapping.platform_product_id == payload.platform_product_id,
            PlatformMapping.is_deleted.is_(False),
            PlatformMapping.sku_id != payload.sku_id,
        )
    ).first()
    if other_active is not None:
        raise ConflictError("O anuncio ja esta vinculado a outro SKU.")

    mapping = _ensure_mapping(
        session,
        tenant_id,
        sku=sku,
        platform=payload.platform,
        platform_sku=payload.platform_sku,
        platform_product_id=payload.platform_product_id,
        platform_variant_id=payload.platform_variant_id,
        allow_user_recovery=True,
    )

    warning = None
    if payload.platform == Platform.mercadolivre:
        try:
            await integrations_client.update_seller_custom_field(
                tenant_id, payload.platform_product_id, sku.internal_sku
            )
        except APIError:
            warning = PlatformMappingWarning(
                code="platform_sku_update_failed",
                message=(
                    "Local link created successfully, but seller_custom_field "
                    "could not be updated on Mercado Livre."
                ),
            )

    return PlatformMappingRelinkResponse(
        mapping=PlatformMappingRead.model_validate(mapping),
        warning=warning,
    )


@router.get("/{mapping_id}", response_model=PlatformMappingRead)
def get_platform_mapping(
    mapping_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> PlatformMapping:
    return _get_mapping_or_404(session, mapping_id, tenant_id)


@router.delete("/{mapping_id}", status_code=204)
async def delete_platform_mapping(
    mapping_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
):
    """Soft delete the mapping (idempotent), pausing/zeroing the listing first.

    The remote mutation happens before the local soft delete so a timeout never
    leaves an orphan link. ``closed``/``404`` listings are simply unlinked.
    """
    mapping = _get_mapping_or_404(
        session, mapping_id, tenant_id, include_deleted=True
    )
    if mapping.is_deleted:
        return

    if (
        mapping.platform == Platform.mercadolivre
        and mapping.platform_product_id
    ):
        await integrations_client.prepare_item_unlink(
            tenant_id, mapping.platform_product_id
        )

    mapping.is_deleted = True
    mapping.is_active = False
    mapping.deleted_reason = DELETED_REASON_USER
    mapping.updated_at = datetime.now(UTC)
    session.add(mapping)
    session.commit()


# =============================================================================
# Internal (service-to-service) endpoints
# =============================================================================


@internal_router.post("", response_model=PlatformMappingRead)
def upsert_internal_platform_mapping(
    payload: PlatformMappingInternalCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_internal_tenant_id),
) -> PlatformMapping:
    """Create or reactivate a mapping after an orchestrated listing creation.

    The integrations-service calls this endpoint once the marketplace listing
    exists. A soft-deleted row for the same ``(tenant_id, platform,
    platform_product_id)`` is resurrected according to the Plan 9 resolution
    matrix; a user-deleted row returns ``409`` so an automatic sync never
    overrides an explicit user decision.
    """
    sku = _validate_sku_for_tenant(session, payload.sku_id, tenant_id)
    return _ensure_mapping(
        session,
        tenant_id,
        sku=sku,
        platform=payload.platform,
        platform_sku=payload.platform_sku,
        platform_product_id=payload.platform_product_id,
        platform_variant_id=payload.platform_variant_id,
    )


@internal_router.post("/unbind", response_model=dict)
def unbind_internal_platform_mapping(
    payload: PlatformMappingUnbind,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_internal_tenant_id),
) -> dict:
    """Soft delete mappings of listings that no longer exist.

    Accepts a single ``platform_product_id`` (Plan 7 listing deletion) or a
    batch ``platform_product_ids`` (Plan 8 reconciliation). Idempotent: calling
    it again returns ``{"unbound": 0}``. Only Mercado Livre mappings are
    targeted because the payload identifies the listing by its ML id and has
    no platform field (per the public contract).
    """
    product_ids = set(payload.platform_product_ids)
    if payload.platform_product_id:
        product_ids.add(payload.platform_product_id)
    if not product_ids:
        return {"unbound": 0}

    mappings = list(
        session.exec(
            select(PlatformMapping).where(
                PlatformMapping.tenant_id == tenant_id,
                PlatformMapping.platform == Platform.mercadolivre,
                PlatformMapping.platform_product_id.in_(product_ids),
                PlatformMapping.is_deleted.is_(False),
            )
        ).all()
    )
    now = datetime.now(UTC)
    for mapping in mappings:
        mapping.is_deleted = True
        mapping.is_active = False
        mapping.deleted_reason = payload.reason
        mapping.updated_at = now
        session.add(mapping)
    if mappings:
        session.commit()
    return {"unbound": len(mappings)}


@internal_router.post("/state", response_model=dict)
def sync_internal_mapping_state(
    payload: PlatformMappingStateUpdate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_internal_tenant_id),
) -> dict:
    """Sync ``is_active`` with a Mercado Livre lifecycle event.

    Stale events (older than the mapping's ``updated_at``) are ignored so an
    out-of-order ``items_changed`` delivery cannot overwrite newer state.
    """
    mappings = list(
        session.exec(
            select(PlatformMapping).where(
                PlatformMapping.tenant_id == tenant_id,
                PlatformMapping.platform == payload.platform,
                PlatformMapping.platform_product_id == payload.platform_product_id,
                PlatformMapping.is_deleted.is_(False),
            )
        ).all()
    )
    event_ts = _as_utc(payload.event_timestamp)
    now = datetime.now(UTC)
    updated = 0
    reactivated_sku_ids: set[int] = set()
    for mapping in mappings:
        mapping_ts = _as_utc(mapping.updated_at)
        if event_ts is not None and mapping_ts is not None and mapping_ts > event_ts:
            continue
        if mapping.is_active == payload.is_active:
            continue
        if payload.is_active:
            reactivated_sku_ids.add(mapping.sku_id)
        mapping.is_active = payload.is_active
        mapping.updated_at = now
        session.add(mapping)
        updated += 1
    if updated:
        session.commit()

    # Plan 10: a listing that became active again needs its current local
    # stock pushed immediately (the flusher intentionally skips inactive ones).
    for sku_id in reactivated_sku_ids:
        sku = session.get(SKU, sku_id)
        if sku is None or sku.is_deleted:
            continue
        product = session.get(Product, sku.product_id)
        if product is None or product.is_deleted:
            continue
        _publish_reactivation_stock(sku)

    return {"updated": updated}

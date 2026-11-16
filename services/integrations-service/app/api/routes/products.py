import logging
from datetime import UTC, datetime, timedelta
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import get_tenant_id
from app.core.errors import APIError
from app.db.session import get_session
from app.models.marketplace_credential import (
    Marketplace,
    MarketplaceCredential,
    MarketplaceItem,
)
from app.schemas.marketplace_credential import (
    CategoryAttributesResponse,
    CategoryAttributeValue,
    CreateListingRequest,
    CreateListingResponse,
    CredentialResponse,
    ItemDescriptionRequest,
    ItemUpdateRequest,
    MLCategoryAttributeResponse,
    MLPictureUploadResponse,
)
from app.services.mercadolibre import MercadoLivreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/mercadolivre", tags=["mercadolivre-products"])


# =============================================================================
# Credentials Endpoints
# =============================================================================

class CredentialResponse(BaseModel):
    id: int
    marketplace: str
    account_name: str
    ml_user_id: int | None
    ml_nickname: str | None
    is_active: bool
    expires_at: str | None
    created_at: str
    updated_at: str


@router.get("/credentials", response_model=List[CredentialResponse])
def list_credentials(
    request: Request,
    session: Session = Depends(get_session),
):
    """List Mercado Livre credentials for the authenticated tenant."""
    tenant_id = get_tenant_id(request)
    
    credentials = session.exec(
        select(MarketplaceCredential).where(
            MarketplaceCredential.tenant_id == tenant_id,
            MarketplaceCredential.marketplace == Marketplace.mercadolivre,
        )
    ).all()
    
    return [
        CredentialResponse(
            id=c.id,
            marketplace=c.marketplace,
            account_name=c.account_name,
            ml_user_id=c.ml_user_id,
            ml_nickname=c.ml_nickname,
            is_active=c.is_active,
            expires_at=c.expires_at.isoformat() if c.expires_at else None,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in credentials
    ]


@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Delete a Mercado Livre credential connection."""
    tenant_id = get_tenant_id(request)
    
    credential = session.get(MarketplaceCredential, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    
    if credential.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this credential")
    
    session.delete(credential)
    session.commit()
    
    return {"message": "Mercado Livre connection removed successfully"}


# =============================================================================
# Category Attributes Endpoint
# =============================================================================

@router.get("/categories/{category_id}/attributes", response_model=list[CategoryAttributeValue])
async def get_category_attributes(
    category_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get category attributes from Mercado Livre (cached for 24h)."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")
    
    try:
        attributes = await ml_service.get_category_attributes(credential.access_token, category_id)
        return attributes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch category attributes: {str(e)}")


# =============================================================================
# Site Categories (árvore de categorias do Mercado Livre)
# =============================================================================

@router.get("/categories", response_model=list[dict[str, Any]])
async def list_site_categories(
    request: Request,
    session: Session = Depends(get_session),
):
    """List the site's categories (GET /sites/MLB/categories) for tree navigation."""
    tenant_id = get_tenant_id(request)

    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")

    try:
        return await ml_service.get_site_categories(credential.access_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list site categories: {str(e)}")


@router.get("/categories/{category_id}", response_model=dict[str, Any])
async def get_category(
    category_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get category details including children (GET /categories/{id}) for tree navigation."""
    tenant_id = get_tenant_id(request)

    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")

    try:
        return await ml_service.get_category(credential.access_token, category_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get category: {str(e)}")


# =============================================================================
# Item Endpoints (User Products v3)
# =============================================================================

@router.post("/listings", response_model=CreateListingResponse, status_code=201)
async def create_listing(
    request: Request,
    payload: CreateListingRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """Create a listing, its description and local links in one operation.

    This replaces the old ``POST /items`` endpoint. The saga is idempotent per
    SKU: a retry returns ``200`` with the already published item and mapping
    instead of creating a duplicate listing on Mercado Livre.
    """
    tenant_id = get_tenant_id(request)

    if payload.children or payload.variations:
        raise APIError(
            status_code=422,
            code="variations_not_supported",
            message="Variations are not supported",
        )

    ml_service = MercadoLivreService(session)

    try:
        item, mapping, existing = await ml_service.create_orchestrated_listing(
            tenant_id, payload.model_dump(exclude_none=True)
        )
    except APIError:
        raise
    except Exception as e:
        logger.exception("Erro crítico ao publicar anúncio no Mercado Livre: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to create listing: {str(e)}"
        ) from e

    if existing:
        response.status_code = 200
    return CreateListingResponse(item=item, mapping=mapping, existing=existing)


@router.post("/items/{item_id}/description", response_model=dict)
async def create_ml_item_description(
    item_id: str,
    request: Request,
    payload: ItemDescriptionRequest,
    session: Session = Depends(get_session),
):
    """Create or replace the description of an item (POST /items/{id}/description, v3)."""
    tenant_id = get_tenant_id(request)

    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")

    try:
        return await ml_service.create_item_description(
            credential.access_token, item_id, payload.plain_text
        )
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create description: {str(e)}")


@router.get("/items/{item_id}/description", response_model=dict)
async def get_ml_item_description(
    item_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Fetch the full description text for an item.

    Returns ``{"description": null}`` when ML returns 404 (no description
    registered). Raises HTTP 503 on timeout/5xx so the frontend can disable
    only the description field while still allowing price/stock edits.
    """
    tenant_id = get_tenant_id(request)

    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")

    try:
        description = await ml_service._fetch_item_description_plain_text(
            credential.access_token, item_id
        )
    except APIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch description: {str(e)}")

    return {"description": description}


@router.get("/items", response_model=dict)
async def list_ml_items(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    search: str | None = Query(None),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """List Mercado Livre items with pagination."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    
    try:
        result = await ml_service.list_items(tenant_id, page, limit, search, status)
        return {
            "items": result["items"],
            "page": result["page"],
            "limit": result["limit"],
            "total": result["total"],
            "total_pages": result["total_pages"],
        }
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list items: {str(e)}")


@router.get("/items/local", response_model=dict)
def list_local_ml_items(
    request: Request,
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    unmapped_only: bool = Query(False),
):
    """List locally synced marketplace items for the authenticated tenant.

    Standard pagination contract (page/limit/total/total_pages). ``is_mapped``
    is derived from the local mirror (a listing carries ``sku_id`` once it is
    linked), so the UI can highlight listings that lost their link.
    """
    tenant_id = get_tenant_id(request)

    filters = [
        MarketplaceItem.tenant_id == tenant_id,
        MarketplaceItem.is_deleted.is_(False),
    ]
    if unmapped_only:
        filters.append(MarketplaceItem.sku_id.is_(None))
    if search:
        term = search.strip()
        if term:
            pattern = f"%{term.lower()}%"
            filters.append(
                or_(
                    func.lower(MarketplaceItem.title).like(pattern),
                    func.lower(MarketplaceItem.item_id).like(pattern),
                )
            )

    total = int(
        session.exec(
            select(func.count())
            .select_from(MarketplaceItem)
            .where(*filters)
        ).one()
    )
    items = session.exec(
        select(MarketplaceItem)
        .where(*filters)
        .order_by(MarketplaceItem.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    return {
        "items": [
            {
                "item_id": item.item_id,
                "title": item.title,
                "price": item.price,
                "available_quantity": item.available_quantity,
                "status": item.status,
                "is_active": item.is_active,
                "thumbnail": item.thumbnail,
                "permalink": item.permalink,
                "sku_id": item.sku_id,
                "product_id": item.product_id,
                "is_mapped": item.sku_id is not None,
                "updated_at": item.updated_at,
                "is_deleted": item.is_deleted,
            }
            for item in items
        ],
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": (total + limit - 1) // limit if total else 0,
    }


@router.get("/items/{item_id}", response_model=dict)
async def get_ml_item(
    item_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get single item details, merged with locally stored Cloudinary URLs."""
    tenant_id = get_tenant_id(request)

    ml_service = MercadoLivreService(session)

    try:
        item = await ml_service.get_item(tenant_id, item_id)

        # Merge locally persisted Cloudinary URLs so the frontend can use them
        # as `source` on update (ML CDN secure_urls cannot be downloaded by ML).
        local_item = session.exec(
            select(MarketplaceItem).where(
                MarketplaceItem.item_id == item_id,
                MarketplaceItem.tenant_id == tenant_id,
            )
        ).first()
        if local_item and isinstance(local_item.raw_payload, dict):
            cloudinary_urls = local_item.raw_payload.get("_cloudinary_urls")
            if cloudinary_urls:
                item["_cloudinary_urls"] = cloudinary_urls

        return item
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get item: {str(e)}")


@router.put("/items/{item_id}", response_model=dict)
async def update_ml_item(
    item_id: str,
    request: Request,
    payload: ItemUpdateRequest,
    session: Session = Depends(get_session),
):
    """Update an existing listing (only editable fields)."""
    tenant_id = get_tenant_id(request)

    if payload.children or payload.variations:
        raise APIError(
            status_code=422,
            code="variations_not_supported",
            message="Variations are not supported",
        )
    
    ml_service = MercadoLivreService(session)
    
    try:
        result = await ml_service.update_item(tenant_id, item_id, payload.model_dump(exclude_none=True))

        # Plan 10: ML may answer a successful PUT with a partial body (no
        # ``status``). The requested status is authoritative for the local
        # mirror and the catalog mapping, otherwise a pause could leave the
        # mapping active and keep blocking the product deletion.
        if not result.get("status") and payload.status:
            result["status"] = payload.status

        # Preserve Cloudinary URLs for local edit/recovery.
        # ML only returns its own CDN secure_urls; we need Cloudinary URLs as
        # `source` for future updates. Keep existing ones if the user didn't
        # change images.
        if payload.pictures is not None:
            result["_cloudinary_urls"] = [p.source for p in payload.pictures]
        elif result.get("_cloudinary_urls"):
            pass  # keep existing _cloudinary_urls from ML response (if any)

        # Sync to local database
        credential = await ml_service.get_valid_credential(tenant_id)
        if credential:
            ml_service.sync_item_to_local(
                credential.tenant_id, result, credential.ml_user_id
            )

        # Plan 10: keep the catalog mapping lifecycle in sync with explicit
        # user actions (pause/activate). This is what makes a paused listing
        # eligible for product deletion without waiting for a webhook.
        if result.get("status"):
            await ml_service.sync_catalog_mapping_state(
                tenant_id, item_id, result.get("status") == "active"
            )
        return result
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update item: {str(e)}")


@router.delete("/items/{item_id}")
async def delete_ml_item(
    item_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Delete an item on Mercado Livre and soft delete its local links.

    A ``404`` from Mercado Livre means the listing is already gone and is
    treated as success. If the remote deletion fails, nothing is changed
    locally. After a successful remote deletion the local MarketplaceItem is
    soft deleted and the catalog mapping is unbound with
    ``deleted_reason=listing_deleted``.
    """
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    
    try:
        await ml_service.delete_item(tenant_id, item_id)

        # Soft delete local mirror instead of destroying history.
        item = session.exec(
            select(MarketplaceItem).where(
                MarketplaceItem.tenant_id == tenant_id,
                MarketplaceItem.item_id == item_id,
            )
        ).first()
        if item and not item.is_deleted:
            item.is_deleted = True
            item.updated_at = datetime.now(UTC)
            session.add(item)
            session.commit()

        # Unbind only after the remote deletion succeeded. A failure here is
        # retryable: a subsequent DELETE receives 404 and repeats this step.
        await ml_service.unbind_catalog_mapping(
            tenant_id, item_id, reason="listing_deleted"
        )

        return {"message": "Item deleted successfully"}
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete item: {str(e)}")


# =============================================================================
# Picture Upload Endpoint
# =============================================================================

class PictureUploadRequest(BaseModel):
    source: str  # Cloudinary URL


@router.post("/pictures", response_model=MLPictureUploadResponse)
async def upload_picture(
    request: Request,
    payload: PictureUploadRequest,
    session: Session = Depends(get_session),
):
    """Upload a picture to Mercado Livre CDN via Cloudinary URL."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")
    
    try:
        secure_url = await ml_service.upload_picture(credential.access_token, payload.source)
        return MLPictureUploadResponse(secure_url=secure_url)
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload picture: {str(e)}")


# =============================================================================
# Category Attributes Response Endpoint (with metadata)
# =============================================================================

@router.get("/categories/{category_id}/attributes/full", response_model=MLCategoryAttributeResponse)
async def get_category_attributes_full(
    category_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get category attributes with metadata (cached for 24h)."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    credential = await ml_service.get_valid_credential(tenant_id)
    if not credential:
        raise HTTPException(status_code=401, detail="No valid Mercado Livre credential found")
    
    try:
        attributes = await ml_service.get_category_attributes(credential.access_token, category_id)
        # Extract category name from attributes if available
        category_name = attributes[0].get("category_name", "Unknown") if attributes else "Unknown"
        return MLCategoryAttributeResponse(
            category_id=category_id,
            category_name=category_name,
            attributes=attributes,
            cached_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch category attributes: {str(e)}")
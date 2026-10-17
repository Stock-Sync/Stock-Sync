from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Any, List
from sqlmodel import Session, select
from jose import jwt, JWTError
from datetime import datetime, timedelta
import logging

from app.core.config import settings
from app.core.errors import APIError
from app.db.session import get_session
from app.models.marketplace_credential import MarketplaceCredential, Marketplace, MarketplaceItem
from app.services.mercadolibre import MercadoLivreService
from app.schemas.marketplace_credential import (
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemDescriptionRequest,
    ItemResponse,
    ItemListResponse,
    CredentialResponse,
    MLPictureUploadResponse,
    CategoryAttributesResponse,
    CategoryAttributeValue,
    MLCategoryAttributeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations/mercadolivre", tags=["mercadolivre-products"])


def get_tenant_id(request: Request) -> str:
    """Extract tenant_id from authenticated request.
    
    Priority:
    1. X-Tenant-ID header (service-to-service)
    2. tenant_id cookie (explicit)
    3. access_token cookie (JWT from auth-service) - DECODE JWT
    """
    # 1. Header (service-to-service)
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id
    
    # 2. Explicit tenant_id cookie
    tenant_id = request.cookies.get("tenant_id")
    if tenant_id:
        return tenant_id
    
    # 3. Extract from access_token JWT (auth-service cookie)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = jwt.decode(
                access_token, 
                settings.jwt_secret_key, 
                algorithms=[settings.jwt_algorithm]
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                return tenant_id
        except JWTError:
            pass  # Invalid token, continue to next method
    
    raise HTTPException(status_code=401, detail="Tenant ID not found")


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

@router.post("/items", response_model=dict)
async def create_ml_item(
    request: Request,
    payload: ItemCreateRequest,
    session: Session = Depends(get_session),
):
    """Create a new listing via User Products v3 API."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    
    try:
        result = await ml_service.create_item_v3(tenant_id, payload.model_dump(exclude_none=True))
        # Sync to local database
        credential = await ml_service.get_valid_credential(tenant_id)
        if credential:
            ml_service.sync_item_to_local(credential.tenant_id, result, credential.ml_user_id)
        return result
    except APIError:
        raise
    except Exception as e:
        logger.exception("Erro crítico ao criar item no Mercado Livre: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create item: {str(e)}")


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


@router.get("/items", response_model=ItemListResponse)
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
        return ItemListResponse(
            items=[ItemResponse.model_validate(item) for item in result["items"]],
            page=result["page"],
            limit=result["limit"],
            total=result["total"],
            total_pages=result["total_pages"],
        )
    except APIError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list items: {str(e)}")


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_ml_item(
    item_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get single item details."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    
    try:
        item = await ml_service.get_item(tenant_id, item_id)
        return ItemResponse.model_validate(item)
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
    
    ml_service = MercadoLivreService(session)
    
    try:
        result = await ml_service.update_item(tenant_id, item_id, payload.model_dump(exclude_none=True))
        # Sync to local database
        credential = await ml_service.get_valid_credential(tenant_id)
        if credential:
            ml_service.sync_item_to_local(credential.tenant_id, result, credential.ml_user_id)
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
    """Delete/pause an item on Mercado Livre."""
    tenant_id = get_tenant_id(request)
    
    ml_service = MercadoLivreService(session)
    
    try:
        await ml_service.delete_item(tenant_id, item_id)
        
        # Also delete from local database
        item = session.exec(
            select(MarketplaceItem).where(
                MarketplaceItem.tenant_id == tenant_id,
                MarketplaceItem.item_id == item_id,
            )
        ).first()
        if item:
            session.delete(item)
            session.commit()
        
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
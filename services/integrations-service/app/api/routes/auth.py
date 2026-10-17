from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session
from jose import jwt, JWTError

from app.core.config import settings
from app.core.errors import UnauthorizedError
from app.db.session import get_session
from app.services.mercadolibre import MercadoLivreService

router = APIRouter(prefix="/api/v1/auth/mercadolivre", tags=["mercadolivre-auth"])


def get_tenant_id_from_request(request: Request) -> str:
    """Extract tenant_id from authenticated request.
    
    Priority:
    1. X-Tenant-ID header (service-to-service)
    2. tenant_id cookie (explicit)
    3. access_token cookie (JWT from auth-service) - DECODE JWT
    4. state query param (for callback)
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
    
    # 4. State param (OAuth callback)
    tenant_id = request.query_params.get("state")
    if tenant_id:
        return tenant_id
    
    raise UnauthorizedError("Tenant ID not found. Please authenticate first.")


@router.get("/connect")
def ml_connect(request: Request, session: Session = Depends(get_session)):
    """Generate Mercado Livre OAuth URL for the authenticated tenant."""
    tenant_id = get_tenant_id_from_request(request)
    
    ml_service = MercadoLivreService(session)
    auth_url = ml_service.get_auth_url(tenant_id)
    
    return {"auth_url": auth_url, "tenant_id": tenant_id}


@router.get("/callback")
async def ml_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
):
    """Handle Mercado Livre OAuth callback."""
    tenant_id = state
    
    ml_service = MercadoLivreService(session)
    
    # Exchange code for tokens
    token_data = await ml_service.exchange_code_for_tokens(code, tenant_id)
    
    # Get user info to extract ml_user_id
    user_info = await ml_service.get_user_info(token_data["access_token"])
    
    # Save credential
    credential = ml_service.save_credential(tenant_id, token_data, user_info)
    
    return {
        "message": "Mercado Livre account connected successfully",
        "credential_id": credential.id,
        "ml_user_id": credential.ml_user_id,
        "account_name": credential.account_name,
    }
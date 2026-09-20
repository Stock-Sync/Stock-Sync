"""
Rotas de autenticação OAuth para Mercado Livre e Shopee.

GET  /auth/{platform}/url      — Gera URL de autorização para redirecionar o vendedor.
POST /auth/{platform}/callback — Recebe o code, troca por tokens e persiste no banco.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import encrypt
from app.db.session import get_session
from app.models.integration import TenantIntegration
from app.schemas.integration import AuthURLResponse, CallbackRequest, IntegrationOut
from app.services.mercadolibre import ml_client
from app.services.shopee import shopee_client

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_PLATFORMS = {"mercadolivre", "shopee"}


def _get_platform_or_404(platform: str) -> str:
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=404,
            detail=f"Plataforma '{platform}' não suportada. Use: {SUPPORTED_PLATFORMS}",
        )
    return platform


# ── GET /auth/{platform}/url ──────────────────────────────────────────────────

@router.get("/{platform}/url", response_model=AuthURLResponse)
def get_auth_url(
    platform: str,
    user_id: uuid.UUID = Query(..., description="UUID do tenant/usuário no SaaS."),
):
    """
    Retorna a URL de autorização OAuth do marketplace solicitado.

    O frontend deve redirecionar o navegador do vendedor para esta URL.
    O parâmetro `state` embutido na URL é o user_id — devolvido no callback
    para associar o código ao tenant correto.
    """
    _get_platform_or_404(platform)
    user_id_str = str(user_id)

    if platform == "mercadolivre":
        auth_url = ml_client.get_auth_url(user_id_str)
    else:
        auth_url = shopee_client.get_auth_url(user_id_str)

    logger.info("Auth URL gerada para platform=%s user_id=%s", platform, user_id_str)
    return AuthURLResponse(platform=platform, auth_url=auth_url)


# ── POST /auth/{platform}/callback ────────────────────────────────────────────

@router.post("/{platform}/callback", response_model=IntegrationOut, status_code=201)
def handle_callback(
    platform: str,
    body: CallbackRequest,
    db: Session = Depends(get_session),
):
    """
    Recebe o authorization code do frontend e conclui o fluxo OAuth.

    Pipeline:
      1. Troca o code por access_token + refresh_token (server-to-server)
      2. Busca o external_seller_id (/users/me no ML, /shop/get_shop_info na Shopee)
      3. Criptografa os tokens
      4. Faz upsert em tenant_integrations (cria ou atualiza por user_id + platform)
      5. Retorna IntegrationOut (sem tokens)
    """
    _get_platform_or_404(platform)

    if not body.state:
        raise HTTPException(
            status_code=400,
            detail="Parâmetro 'state' (user_id) é obrigatório no callback OAuth.",
        )

    try:
        user_id = uuid.UUID(body.state)
    except ValueError:
        raise HTTPException(status_code=400, detail="'state' inválido — não é um UUID válido.")

    try:
        if platform == "mercadolivre":
            token_data = ml_client.exchange_code(body.code)
            access_token = token_data["access_token"]
            refresh_token = token_data["refresh_token"]
            expires_at = ml_client.calculate_expiry(token_data.get("expires_in", 21600))
            user_info = ml_client.get_user_info(access_token)
            external_seller_id = str(user_info["id"])

        else:  # shopee
            if not body.shop_id:
                raise HTTPException(
                    status_code=400,
                    detail="'shop_id' é obrigatório no callback da Shopee.",
                )
            token_data = shopee_client.exchange_code(body.code, body.shop_id)
            access_token = token_data["access_token"]
            refresh_token = token_data["refresh_token"]
            expires_at = shopee_client.calculate_expiry(token_data.get("expire_in", 14400))
            external_seller_id = str(body.shop_id)

    except Exception as exc:
        logger.error(
            "Falha ao trocar code por tokens — platform=%s: %s", platform, exc, exc_info=True
        )
        raise HTTPException(
            status_code=502,
            detail=f"Falha na comunicação com a API do marketplace: {exc}",
        )

    # Criptografar tokens antes de persistir
    access_token_enc = encrypt(access_token)
    refresh_token_enc = encrypt(refresh_token)

    # Upsert: busca integração existente ou cria nova
    existing = (
        db.query(TenantIntegration)
        .filter_by(user_id=user_id, platform=platform)
        .first()
    )

    if existing:
        existing.external_seller_id = external_seller_id
        existing.access_token_encrypted = access_token_enc
        existing.refresh_token_encrypted = refresh_token_enc
        existing.access_token_expires_at = expires_at
        integration = existing
        logger.info(
            "Integração atualizada — platform=%s user_id=%s seller_id=%s",
            platform, user_id, external_seller_id,
        )
    else:
        integration = TenantIntegration(
            user_id=user_id,
            platform=platform,
            external_seller_id=external_seller_id,
            access_token_encrypted=access_token_enc,
            refresh_token_encrypted=refresh_token_enc,
            access_token_expires_at=expires_at,
        )
        db.add(integration)
        logger.info(
            "Nova integração criada — platform=%s user_id=%s seller_id=%s",
            platform, user_id, external_seller_id,
        )

    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)

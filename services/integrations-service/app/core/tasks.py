"""
Background jobs do integrations-service usando APScheduler.

Job configurado:
  - `refresh_expiring_tokens`: Roda a cada 30 minutos.
    Busca tokens que expiram nos próximos 60 minutos e os renova via API do marketplace.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.security import decrypt, encrypt
from app.db.session import SessionLocal
from app.models.integration import TenantIntegration
from app.services.mercadolibre import ml_client
from app.services.shopee import shopee_client

logger = logging.getLogger(__name__)

# Renova tokens que expiram nos próximos N minutos
REFRESH_AHEAD_MINUTES = 60


def refresh_expiring_tokens() -> None:
    """
    Job de renovação automática de tokens OAuth.

    Executado a cada 30 minutos pelo APScheduler.
    Consulta tenant_integrations buscando tokens próximos de expirar,
    renova via API do marketplace correspondente e persiste no banco.
    """
    logger.info("Job refresh_expiring_tokens iniciado.")
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_AHEAD_MINUTES)

    with SessionLocal() as db:
        integrations = (
            db.query(TenantIntegration)
            .filter(TenantIntegration.access_token_expires_at <= cutoff)
            .all()
        )

        if not integrations:
            logger.info("Nenhum token próximo de expirar. Job encerrado.")
            return

        logger.info("%d token(s) para renovar.", len(integrations))

        for integration in integrations:
            try:
                refresh_token_plain = decrypt(integration.refresh_token_encrypted)

                if integration.platform == "mercadolivre":
                    token_data = ml_client.refresh_token(refresh_token_plain)
                    new_access = token_data["access_token"]
                    new_refresh = token_data["refresh_token"]
                    new_expires_at = ml_client.calculate_expiry(
                        token_data.get("expires_in", 21600)
                    )

                elif integration.platform == "shopee":
                    shop_id = int(integration.external_seller_id)
                    token_data = shopee_client.refresh_token(refresh_token_plain, shop_id)
                    new_access = token_data["access_token"]
                    new_refresh = token_data["refresh_token"]
                    new_expires_at = shopee_client.calculate_expiry(
                        token_data.get("expire_in", 14400)
                    )

                else:
                    logger.warning(
                        "Plataforma desconhecida '%s' para integração id=%s. Pulando.",
                        integration.platform, integration.id,
                    )
                    continue

                # Atualiza tokens criptografados no banco
                integration.access_token_encrypted = encrypt(new_access)
                integration.refresh_token_encrypted = encrypt(new_refresh)
                integration.access_token_expires_at = new_expires_at
                db.commit()

                logger.info(
                    "Token renovado com sucesso — platform=%s user_id=%s seller_id=%s expires_at=%s",
                    integration.platform,
                    integration.user_id,
                    integration.external_seller_id,
                    new_expires_at.isoformat(),
                )

            except Exception as exc:
                logger.error(
                    "Falha ao renovar token — platform=%s user_id=%s: %s",
                    integration.platform, integration.user_id, exc, exc_info=True,
                )
                db.rollback()
                # Continua processando os demais registros mesmo após falha individual


def create_scheduler() -> BackgroundScheduler:
    """
    Cria e configura o scheduler APScheduler.

    O scheduler usa um BackgroundScheduler (thread pool) — não bloqueia o
    event loop do Uvicorn. O job de refresh roda a cada 30 minutos.
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_expiring_tokens,
        trigger="interval",
        minutes=30,
        id="refresh_expiring_tokens",
        name="Renovação automática de tokens OAuth",
        replace_existing=True,
        max_instances=1,  # evita execuções paralelas do mesmo job
    )
    return scheduler

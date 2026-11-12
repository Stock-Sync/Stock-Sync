from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Any
from sqlmodel import Session
import logging

from app.db.session import get_session
from app.services.mercadolibre import MercadoLivreService

router = APIRouter(prefix="/api/v1/integrations/webhooks", tags=["webhooks"])

logger = logging.getLogger(__name__)


class WebhookNotification(BaseModel):
    user_id: int
    resource: str
    topic: str
    received: str
    sent: str
    attempts: int
    id: str


@router.post("/mercadolivre")
async def ml_webhook(
    request: Request,
    notification: WebhookNotification,
    x_signature: str | None = Header(None),
    session: Session = Depends(get_session),
):
    """Receive Mercado Livre webhook notifications."""

    # Log the notification
    logger.info(
        "mercadolivre_webhook_received",
        extra={
            "user_id": notification.user_id,
            "resource": notification.resource,
            "topic": notification.topic,
            "notification_id": notification.id,
        },
    )

    # Process based on topic
    ml_service = MercadoLivreService(session)

    try:
        if notification.topic == "items" and notification.resource.startswith("/items/"):
            item_id = notification.resource.split("/")[-1]

            # Find credential by ml_user_id from notification
            from app.models.marketplace_credential import MarketplaceCredential, Marketplace
            from sqlmodel import select

            credential = session.exec(
                select(MarketplaceCredential).where(
                    MarketplaceCredential.ml_user_id == notification.user_id,
                    MarketplaceCredential.marketplace == Marketplace.mercadolivre,
                    MarketplaceCredential.is_active == True,
                )
            ).first()

            if credential:
                # Fetch full item details from ML
                item_data = await ml_service.get_item(credential.tenant_id, item_id)

                # Sync to local database
                ml_service.sync_item_to_local(credential.tenant_id, item_data, notification.user_id)

                logger.info(
                    "mercadolivre_item_webhook_processed",
                    extra={
                        "item_id": item_id,
                        "tenant_id": credential.tenant_id,
                        "ml_user_id": notification.user_id,
                    },
                )

        elif notification.topic == "orders" and notification.resource.startswith("/orders/"):
            order_id = notification.resource.split("/")[-1]

            # Dispatch to background processing
            # For now, we'll process synchronously but in production use Redis Stream/Queue
            try:
                await process_order_notification(session, notification.user_id, order_id)
            except Exception as e:
                logger.error(
                    "mercadolivre_webhook_processing_failed",
                    extra={"order_id": order_id, "error": str(e)},
                )
                # Don't raise - we already acknowledged with 200

    except Exception as e:
        logger.error(
            "mercadolivre_webhook_processing_error",
            extra={"error": str(e), "topic": notification.topic, "resource": notification.resource},
        )
        # Don't raise - we already acknowledged with 200

    # Always respond 200 OK to Mercado Livre
    return {"status": "ok"}


async def process_order_notification(session: Session, ml_user_id: int, order_id: str):
    """Process order notification by fetching full order details."""

    # Find credential by ml_user_id
    from app.models.marketplace_credential import MarketplaceCredential, Marketplace
    from sqlmodel import select

    credential = session.exec(
        select(MarketplaceCredential).where(
            MarketplaceCredential.ml_user_id == ml_user_id,
            MarketplaceCredential.marketplace == Marketplace.mercadolivre,
            MarketplaceCredential.is_active == True,
        )
    ).first()

    if not credential:
        logger.warning(
            "mercadolivre_credential_not_found_for_user",
            extra={"ml_user_id": ml_user_id},
        )
        return

    ml_service = MercadoLivreService(session)

    try:
        # Fetch full order details
        order_data = await ml_service.get_order(credential.tenant_id, order_id)

        # TODO: Store order in sales-service or local database
        # For now, just log it
        logger.info(
            "mercadolivre_order_processed",
            extra={
                "order_id": order_id,
                "tenant_id": credential.tenant_id,
                "order_data": order_data,
            },
        )

        # In a real implementation, you would:
        # 1. Send to sales-service via HTTP or message queue
        # 2. Store in local database for sync
        # 3. Trigger any business logic

    except Exception as e:
        logger.error(
            "mercadolivre_order_fetch_failed",
            extra={"order_id": order_id, "error": str(e)},
        )
        raise

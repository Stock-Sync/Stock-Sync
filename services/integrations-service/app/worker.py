"""
Worker do integrations-service — Consumidor do stream `stock:updates`.

Escuta eventos de atualização de estoque publicados pelo sync-service e
executa as chamadas HTTP correspondentes nas APIs dos marketplaces.

Uso:
    python -m app.worker

O worker usa XREADGROUP com blocking read (BLOCK 5000ms) para aguardar
novas mensagens de forma eficiente sem polling ativo.
"""

import logging
import signal
import sys
import time

from app.core.security import decrypt
from app.db.session import SessionLocal
from app.models.integration import TenantIntegration
from app.schemas.integration import StockUpdateEvent
from app.services.mercadolibre import ml_client
from app.services.redis_stream import (
    ack_message,
    ensure_consumer_group,
    read_stock_updates,
)
from app.services.shopee import shopee_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("integrations.worker")

CONSUMER_NAME = "worker-1"
_running = True


def _handle_shutdown(signum, frame):
    """Handler para SIGTERM/SIGINT — encerra o loop graciosamente."""
    global _running
    logger.info("Sinal %d recebido. Encerrando worker...", signum)
    _running = False


def _process_stock_update(message_id: str, data: dict) -> None:
    """
    Processa um único evento de atualização de estoque.

    Pipeline:
      1. Valida o payload com StockUpdateEvent
      2. Busca credenciais ativas do tenant no banco
      3. Descriptografa o access_token
      4. Executa a chamada de atualização de estoque no marketplace
      5. Confirma a mensagem via XACK
    """
    try:
        event = StockUpdateEvent(**data)
    except Exception as exc:
        logger.error(
            "Payload inválido no stream stock:updates — id=%s: %s", message_id, exc
        )
        # Ack mesmo assim para não travar o stream com mensagem malformada
        ack_message(message_id)
        return

    with SessionLocal() as db:
        # Query includes external_seller_id to match unique constraint
        # (user_id, platform, external_seller_id)
        integration = (
            db.query(TenantIntegration)
            .filter_by(
                user_id=event.user_id,
                platform=event.platform,
                external_seller_id=event.external_seller_id,
            )
            .first()
        )

        if not integration:
            logger.warning(
                "Sem integração ativa para user_id=%s platform=%s. Mensagem descartada.",
                event.user_id, event.platform,
            )
            ack_message(message_id)
            return

        try:
            access_token = decrypt(integration.access_token_encrypted)

            if event.platform == "mercadolivre":
                ml_client.update_stock(
                    item_id=event.item_id,
                    quantity=event.quantity,
                    access_token=access_token,
                )
                logger.info(
                    "Estoque ML atualizado — item_id=%s qty=%d user_id=%s",
                    event.item_id, event.quantity, event.user_id,
                )

            elif event.platform == "shopee":
                if not event.shop_id:
                    logger.error(
                        "shop_id ausente para evento Shopee — user_id=%s sku=%s",
                        event.user_id, event.sku,
                    )
                    ack_message(message_id)
                    return

                shopee_client.update_stock(
                    item_id=int(event.item_id),
                    model_id=event.model_id,
                    quantity=event.quantity,
                    access_token=access_token,
                    shop_id=event.shop_id,
                )
                logger.info(
                    "Estoque Shopee atualizado — item_id=%s qty=%d user_id=%s",
                    event.item_id, event.quantity, event.user_id,
                )

        except Exception as exc:
            logger.error(
                "Falha ao atualizar estoque — platform=%s item_id=%s: %s",
                event.platform, event.item_id, exc, exc_info=True,
            )
            # Não faz XACK em caso de erro para reprocessamento futuro
            return

    ack_message(message_id)


def run() -> None:
    """Loop principal do worker."""
    logger.info("Worker de estoque iniciado. Consumer: %s", CONSUMER_NAME)

    # Configura handlers de shutdown gracioso
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Garante que o consumer group existe antes de começar a ler
    ensure_consumer_group()

    while _running:
        try:
            messages = read_stock_updates(
                consumer_name=CONSUMER_NAME,
                count=10,
                block_ms=5000,
            )
            for message_id, data in messages:
                if not _running:
                    break
                logger.debug("Processando mensagem id=%s", message_id)
                _process_stock_update(message_id, data)

        except Exception as exc:
            logger.error("Erro no loop do worker: %s", exc, exc_info=True)
            time.sleep(2)  # backoff antes de tentar novamente

    logger.info("Worker encerrado.")


if __name__ == "__main__":
    run()

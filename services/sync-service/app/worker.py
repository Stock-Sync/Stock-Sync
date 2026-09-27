"""
Worker do sync-service — Consumidor do stream `marketplaces:events`.

Escuta eventos de marketplace publicados pelo integrations-service e
processa a lógica de sincronização de estoque.

Uso:
    python -m app.worker

O worker usa XREADGROUP com blocking read (BLOCK 5000ms) para aguardar
novas mensagens de forma eficiente sem polling ativo.
"""

import logging
import signal
import sys
import time

from app.core.config import settings
from app.services.redis_stream import (
    ensure_marketplace_consumer_group,
    read_marketplace_events,
    ack_marketplace_event,
    claim_pending_messages,
)
from app.services.sync_engine import process_marketplace_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sync.worker")

CONSUMER_NAME = settings.worker_consumer_name
_running = True


def _handle_shutdown(signum, frame):
    """Handler para SIGTERM/SIGINT — encerra o loop graciosamente."""
    global _running
    logger.info("Sinal %d recebido. Encerrando worker...", signum)
    _running = False


def _process_message(message_id: str, data: dict) -> None:
    """
    Processa uma única mensagem do stream marketplaces:events.

    Pipeline:
      1. Valida o payload com MarketplaceEvent
      2. Processa via SyncEngine (determina sincronização, publica em stock:updates)
      3. Confirma a mensagem via XACK
    """
    try:
        success = process_marketplace_event(data)
        if success:
            ack_marketplace_event(message_id)
            logger.debug("Mensagem processada e confirmada: id=%s", message_id)
        else:
            # Se falhou no processamento, não faz XACK para reprocessamento futuro
            logger.warning("Falha no processamento, mensagem não confirmada: id=%s", message_id)
    except Exception as exc:
        logger.error("Erro inesperado ao processar mensagem id=%s: %s", message_id, exc, exc_info=True)
        # Não faz XACK em caso de erro para reprocessamento futuro


def _recover_pending_messages() -> None:
    """
    Tenta recuperar mensagens pendentes de consumidores que morreram.
    Executa uma vez na inicialização.
    """
    logger.info("Verificando mensagens pendentes para recuperação...")
    claimed = claim_pending_messages(
        consumer_name=CONSUMER_NAME,
        min_idle_time_ms=60000,  # 60 segundos ocioso
        count=100,
    )
    if claimed:
        logger.info("Recuperadas %d mensagens pendentes", len(claimed))
        for message_id, data in claimed:
            if not _running:
                break
            logger.debug("Processando mensagem recuperada id=%s", message_id)
            _process_message(message_id, data)
    else:
        logger.info("Nenhuma mensagem pendente para recuperar")


def run() -> None:
    """Loop principal do worker."""
    logger.info("Worker de sincronização iniciado. Consumer: %s", CONSUMER_NAME)

    # Configura handlers de shutdown gracioso
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Garante que o consumer group existe antes de começar a ler
    ensure_marketplace_consumer_group()

    # Tenta recuperar mensagens pendentes na inicialização
    _recover_pending_messages()

    logger.info("Iniciando loop principal de consumo...")

    while _running:
        try:
            messages = read_marketplace_events(
                consumer_name=CONSUMER_NAME,
                count=settings.worker_batch_size,
                block_ms=settings.worker_block_ms,
            )
            for message_id, data in messages:
                if not _running:
                    break
                logger.debug("Processando mensagem id=%s event_type=%s", message_id, data.get("event_type"))
                _process_message(message_id, data)

        except Exception as exc:
            logger.error("Erro no loop do worker: %s", exc, exc_info=True)
            time.sleep(2)  # backoff antes de tentar novamente

    logger.info("Worker encerrado.")


if __name__ == "__main__":
    run()
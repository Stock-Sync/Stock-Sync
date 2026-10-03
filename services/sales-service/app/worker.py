"""
Worker do sales-service — Consumidor do stream `marketplaces:events`.

Escuta eventos de marketplace publicados pelo integrations-service e
processa a lógica de vendas (ordens + métricas).

Uso:
    python -m app.worker

O worker usa XREADGROUP com blocking read (BLOCK 5000ms) para aguardar
novas mensagens de forma eficiente sem polling ativo.
"""

import logging
import signal
import sys
import time

from app.services.redis_stream import (
    ensure_sales_consumer_group,
    read_marketplace_events,
    get_pending_marketplace_events,
    claim_pending_messages,
)
from app.services.sales_engine import process_batch, recover_pending_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sales.worker")

CONSUMER_NAME = "sales-worker-1"
_running = True


def _handle_shutdown(signum, frame):
    """Handler para SIGTERM/SIGINT — encerra o loop graciosamente."""
    global _running
    logger.info("Sinal %d recebido. Encerrando worker...", signum)
    _running = False


def run() -> None:
    """Loop principal do worker."""
    logger.info("Worker de vendas iniciado. Consumer: %s", CONSUMER_NAME)

    # Configura handlers de shutdown gracioso
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Garante que o consumer group existe antes de começar a ler
    ensure_sales_consumer_group()

    # Tenta recuperar mensagens pendentes na inicialização
    recover_pending_events(CONSUMER_NAME)

    logger.info("Iniciando loop principal de consumo...")

    while _running:
        try:
            messages = read_marketplace_events(
                consumer_name=CONSUMER_NAME,
                count=100,
                block_ms=5000,
            )
            if messages:
                logger.debug("Processando batch de %d mensagens", len(messages))
                deltas = process_batch(messages)
                if deltas:
                    logger.info("Batch processado. Deltas: %s", deltas)

        except Exception as exc:
            logger.error("Erro no loop do worker: %s", exc, exc_info=True)
            time.sleep(2)  # backoff antes de tentar novamente

    logger.info("Worker encerrado.")


if __name__ == "__main__":
    run()
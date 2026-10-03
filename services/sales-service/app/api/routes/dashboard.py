"""
Rotas de API para Dashboard em tempo real (SSE).

Endpoints:
  - GET /api/v1/dashboard/stream - Server-Sent Events para atualizações em tempo real
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.services.redis_stream import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Canal Redis para pub/sub de deltas de métricas
METRICS_DELTAS_CHANNEL = "sales:metrics:deltas"

# Clientes SSE conectados
connected_clients: set[asyncio.Queue] = set()


async def metrics_event_generator(request: Request) -> AsyncGenerator[str, None]:
    """
    Generator SSE que envia atualizações de métricas em tempo real.

    Formato do evento:
    event: metrics
    data: {"total_revenue:mercadolivre": 150.0, "total_orders:mercadolivre": 3, ...}
    """
    queue: asyncio.Queue = asyncio.Queue()
    connected_clients.add(queue)

    # Envia evento de conexão
    yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

    # Subscreve ao canal Redis
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    pubsub.subscribe(METRICS_DELTAS_CHANNEL)

    try:
        # Task para ler do pubsub
        async def read_pubsub():
            for message in pubsub.listen():
                if message["type"] == "message":
                    await queue.put(message["data"])

        pubsub_task = asyncio.create_task(read_pubsub())

        while True:
            # Verifica se cliente desconectou
            if await request.is_disconnected():
                break

            try:
                # Aguarda dados com timeout para permitir heartbeat
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: metrics\ndata: {data}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat - envia comentário para manter conexão viva
                yield ": heartbeat\n\n"

    except Exception as exc:
        logger.error("Erro no SSE stream: %s", exc)
        yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
    finally:
        connected_clients.discard(queue)
        pubsub_task.cancel()
        pubsub.unsubscribe(METRICS_DELTAS_CHANNEL)
        pubsub.close()


@router.get("/stream")
async def dashboard_stream(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Endpoint SSE para atualizações em tempo real do dashboard.

    Conexão mantida aberta, recebe eventos 'metrics' com deltas.
    Exemplo de dado:
    {
        "total_revenue:mercadolivre": 150.50,
        "total_orders:mercadolivre": 3,
        "total_items_sold:mercadolivre": 5,
        "sku_revenue:mercadolivre:SKU-123": 99.90
    }
    """
    return StreamingResponse(
        metrics_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Desabilita buffer nginx
        },
    )


def publish_metric_deltas(deltas: dict[str, float]) -> None:
    """
    Publica deltas de métricas no canal Redis para distribuição via SSE.
    Chamado pelo SalesEngine após processar batch.
    """
    if not deltas:
        return

    redis_client = get_redis_client()
    try:
        redis_client.publish(METRICS_DELTAS_CHANNEL, json.dumps(deltas))
        logger.debug("Deltas publicados no canal SSE: %s", deltas)
    except Exception as exc:
        logger.error("Erro ao publicar deltas no Redis: %s", exc)
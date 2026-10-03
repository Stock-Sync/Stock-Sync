import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from app.api.handlers import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.routes import dashboard, metrics, orders
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import get_session
from app.worker import run as run_worker

# Referência global para o thread do worker
_worker_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    
    # Inicia worker em background thread
    global _worker_thread
    _worker_thread = threading.Thread(target=run_worker, daemon=True)
    _worker_thread.start()
    logger.info("Worker de vendas iniciado em background thread.")
    
    yield

    # Shutdown
    logger.info("Aguardando worker encerrar...")
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=10)
    logger.info("Serviço encerrado.")


import logging
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)

# Rotas
app.include_router(orders.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/health/redis")
async def health_redis():
    """Verifica a conectividade com o Redis."""
    import redis
    from app.core.config import settings
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as exc:
        return {"status": "error", "redis": "disconnected", "error": str(exc)}


@app.get("/health/catalog")
async def health_catalog():
    """Verifica a conectividade com o catalog-service."""
    from app.services.catalog_client import catalog_client
    healthy = catalog_client.health_check()
    return {"status": "ok" if healthy else "error", "catalog_service": "connected" if healthy else "disconnected"}
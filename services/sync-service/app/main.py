"""
Entry-point do sync-service.

Inicializa:
  - FastAPI com rotas de API (/api/v1/...)
  - Criação das tabelas no PostgreSQL (via SQLModel metadata)
  - APScheduler para jobs periódicos (limpeza, health checks)
  - Background worker para consumir eventos do Redis Streams
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from app import models  # noqa: F401 — garante que os modelos sejam registrados no metadata
from app.api.routes import api_router
from app.core.config import settings
from app.core.tasks import create_scheduler
from app.db.session import engine, get_session

logger = logging.getLogger(__name__)

# Referência global para o thread do worker
_worker_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do FastAPI: inicializa recursos na subida, libera no shutdown."""
    global _worker_thread

    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("Criando tabelas no banco de dados...")
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas com sucesso.")

    logger.info("Iniciando APScheduler (jobs periódicos)...")
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler iniciado.")

    # Inicia worker em background thread
    logger.info("Iniciando worker de sincronização em background...")
    _worker_thread = threading.Thread(target=run_worker, daemon=True)
    _worker_thread.start()
    logger.info("Worker iniciado em background thread.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Encerrando APScheduler...")
    scheduler.shutdown(wait=False)

    logger.info("Aguardando worker encerrar...")
    # O worker é daemon, então encerra automaticamente com o processo
    # Mas tentamos dar um tempo para shutdown gracioso
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=10)

    logger.info("Serviço encerrado.")


def run_worker() -> None:
    """Executa o worker em uma thread separada."""
    from app.worker import run
    run()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Serviço de orquestração de sincronização de estoque entre canais.",
    lifespan=lifespan,
)

# ── Rotas ─────────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health Checks ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """Verifica se o serviço está rodando."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/health/db", tags=["Health"])
def health_db(session: Session = Depends(get_session)):
    """Verifica a conectividade com o PostgreSQL."""
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/health/redis", tags=["Health"])
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


@app.get("/health/catalog", tags=["Health"])
async def health_catalog():
    """Verifica a conectividade com o catalog-service."""
    from app.services.catalog_client import catalog_client
    healthy = catalog_client.health_check()
    return {"status": "ok" if healthy else "error", "catalog_service": "connected" if healthy else "disconnected"}
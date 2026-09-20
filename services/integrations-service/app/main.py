"""
Entry-point do integrations-service.

Inicializa:
  - FastAPI com as rotas de Auth e Webhooks (/api/v1/...)
  - Criação das tabelas no PostgreSQL (via SQLAlchemy metadata)
  - APScheduler para renovação automática de tokens a cada 30 minutos
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401 — garante que os modelos sejam registrados no metadata
from app.api.routes import api_router
from app.core.config import settings
from app.core.tasks import create_scheduler
from app.db.session import Base, engine, get_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do FastAPI: inicializa recursos na subida, libera no shutdown."""
    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("Criando tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas com sucesso.")

    logger.info("Iniciando APScheduler (job de renovação de tokens)...")
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler iniciado. Próxima execução em 30 minutos.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Encerrando APScheduler...")
    scheduler.shutdown(wait=False)
    logger.info("Serviço encerrado.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Serviço de integração com marketplaces (Mercado Livre e Shopee).",
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

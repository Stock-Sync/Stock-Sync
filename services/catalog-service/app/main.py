from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from app import models  # noqa: F401 (registra as tabelas no metadata)
from app.api.routes import platform_mappings, products, skus
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# Include API routes
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(skus.router)
app.include_router(platform_mappings.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

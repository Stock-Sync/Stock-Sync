from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401 (registra as tabelas no metadata)
from app.api.routes.mappings import router as mappings_router
from app.api.routes.products import router as products_router
from app.core.config import settings
from app.db.session import engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# Include API routes
app.include_router(mappings_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
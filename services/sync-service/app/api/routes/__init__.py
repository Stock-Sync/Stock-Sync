"""
Rotas da API do sync-service.
"""

from fastapi import APIRouter

from app.api.routes.sync import router as sync_router
from app.api.routes.audit import router as audit_router

api_router = APIRouter()
api_router.include_router(sync_router, prefix="/sync", tags=["Sync"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
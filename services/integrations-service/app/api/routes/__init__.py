from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["OAuth"])
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])

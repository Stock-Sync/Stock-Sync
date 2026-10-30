import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from app.api.handlers import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.routes import sync
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import get_session
from app.streams.consumer import EventConsumer
from app.tasks.flusher import QuantityFlusher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    background: list[asyncio.Task] = []
    consumer: EventConsumer | None = None
    flusher: QuantityFlusher | None = None

    if settings.consumer_enabled:
        consumer = EventConsumer()
        background.append(asyncio.create_task(consumer.run(), name="stream-consumer"))
    if settings.flusher_enabled:
        flusher = QuantityFlusher()
        background.append(asyncio.create_task(flusher.run(), name="quantity-flusher"))

    try:
        yield
    finally:
        if consumer is not None:
            await consumer.stop()
        if flusher is not None:
            await flusher.stop()
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        logger.info("background_workers_stopped")


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)
app.include_router(sync.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
def health_db(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

"""Opt-in concurrency test for ``SyncEvent`` deduplication (PostgreSQL only).

SQLite serializes writers and does not reproduce the unique-constraint race, so
the test is opt-in and uses an isolated schema:

    TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
        pytest tests/test_consumer_concurrency.py
"""

import asyncio
import os
import threading
from uuid import uuid4

import pytest
from app.models import SyncEvent
from app.streams.consts import EVENT_STOCK_ADJUST
from app.streams.consumer import EventConsumer
from sqlalchemy import create_engine, func, text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, select

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TEST_POSTGRES_URL to run the PostgreSQL concurrency test",
)


@pytest.fixture()
def pg_engine():
    schema = f"syncevent_dedupe_{uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, poolclass=NullPool)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        POSTGRES_URL,
        connect_args={"options": f"-csearch_path={schema}"},
        poolclass=NullPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.asyncio
async def test_concurrent_get_or_create_keeps_a_single_row(pg_engine):
    consumer = EventConsumer(
        redis_client=object(),
        session_factory=lambda: Session(pg_engine),
    )
    dedupe_key = "concurrent-dedupe"
    payload = {"sku_id": 1, "new_quantity": 2}
    barrier = threading.Barrier(2)

    def deliver() -> SyncEvent:
        barrier.wait(timeout=10)
        return consumer._get_or_create_event(EVENT_STOCK_ADJUST, dedupe_key, payload)

    results = await asyncio.gather(*(asyncio.to_thread(deliver) for _ in range(2)))

    assert len(results) == 2
    assert all(result.id is not None for result in results)
    assert all(result.dedupe_key == dedupe_key for result in results)

    with Session(pg_engine) as session:
        count = session.exec(select(func.count()).select_from(SyncEvent)).one()
        stored = session.exec(
            select(SyncEvent).where(SyncEvent.dedupe_key == dedupe_key)
        ).one()

    assert count == 1
    assert stored.event_type == EVENT_STOCK_ADJUST

"""Opt-in concurrency test for the Order upsert (requires TEST_POSTGRES_URL).

Run with a disposable PostgreSQL database, for example:

    TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5433/postgres \
        pytest tests/test_orders_concurrency.py
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models import Order
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="set TEST_POSTGRES_URL to run the PostgreSQL concurrency test",
)

SCHEMA = "stocksync_orders_concurrency"


def _sale_payload() -> dict:
    return {
        "tenant_id": "tenant-1",
        "marketplace": "mercado_livre",
        "marketplace_order_id": "ML-100",
        "marketplace_item_id": "MLB-1",
        "internal_sku": "SKU-1",
        "sku_id": 7,
        "item_title": "Fone Bluetooth",
        "buyer_nickname": "joao-buyer",
        "quantity": 2,
        "unit_price": 50.0,
        "total_amount": 100.0,
        "currency": "BRL",
        "status": "paid",
        "is_variation": False,
        "ordered_at": "2026-10-23T12:00:00Z",
    }


def test_concurrent_upsert_keeps_a_single_row(monkeypatch):
    admin = create_engine(TEST_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))

    engine = create_engine(
        TEST_POSTGRES_URL,
        connect_args={"options": f"-csearch_path={SCHEMA}"},
        poolclass=NullPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(settings, "internal_service_secret", "test-secret")

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    barrier = threading.Barrier(5)

    def call() -> int:
        barrier.wait()
        with TestClient(app) as client:
            return client.post(
                "/api/v1/orders/internal",
                json=_sale_payload(),
                headers={
                    "X-Internal-Secret": "test-secret",
                    "X-Tenant-ID": "tenant-1",
                },
            ).status_code

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            statuses = list(executor.map(lambda _: call(), range(5)))

        assert statuses == [201] * 5
        with Session(engine) as session:
            count = session.exec(select(func.count()).select_from(Order)).one()[0]
            assert count == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        admin.dispose()

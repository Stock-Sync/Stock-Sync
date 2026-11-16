"""Row-lock regression test for ``POST /api/v1/skus/{id}/adjust``.

SQLite ignores ``SELECT ... FOR UPDATE``, so the serialization guarantee can
only be exercised against PostgreSQL. The test is opt-in:

    TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5433/postgres \
        pytest tests/test_skus_concurrency.py

Each test uses an isolated schema and drops it afterwards, so it never touches
the application tables of the target database.
"""

import os
import threading
from uuid import uuid4

import app.api.routes.skus as skus_module
import pytest
from app.models import SKU, Product
from app.schemas import SKUAdjust
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="TEST_POSTGRES_URL not set (PostgreSQL only)"
)


@pytest.fixture()
def pg_engine():
    schema = f"adjust_test_{uuid4().hex[:12]}"
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


def _create_sku(engine, stock_quantity: int) -> int:
    with Session(engine) as session:
        product = Product(tenant_id="tenant-1", name="Produto")
        session.add(product)
        session.commit()
        session.refresh(product)

        sku = SKU(
            tenant_id="tenant-1",
            product_id=product.id,
            internal_sku="SKU-CONCURRENT",
            stock_quantity=stock_quantity,
        )
        session.add(sku)
        session.commit()
        session.refresh(sku)
        return sku.id


def test_concurrent_deductions_report_serialized_quantities(pg_engine):
    """Two simultaneous ``-2`` adjustments must each see the previous write."""
    sku_id = _create_sku(pg_engine, stock_quantity=10)

    barrier = threading.Barrier(2)
    results: list = []

    def worker() -> None:
        with Session(pg_engine) as session:
            barrier.wait(timeout=10)
            results.append(
                skus_module.adjust_sku_stock(
                    sku_id,
                    SKUAdjust(delta=-2, source="ml_sale"),
                    session,
                    "tenant-1",
                )
            )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert len(results) == 2
    # The row lock serializes the transitions: 10 -> 8 and 8 -> 6. Without it
    # both responses would report previous_quantity=10 and deducted 2/4.
    assert sorted(result.previous_quantity for result in results) == [8, 10]
    assert sorted(result.new_quantity for result in results) == [6, 8]
    assert all(result.clamped is False for result in results)

    with Session(pg_engine) as session:
        stored = session.get(SKU, sku_id)
        assert stored is not None
        assert stored.stock_quantity == 6


def test_concurrent_clamp_reports_the_actual_removal(pg_engine):
    """A clamped adjustment must not report stock that was never removed."""
    sku_id = _create_sku(pg_engine, stock_quantity=1)

    barrier = threading.Barrier(2)
    results: list = []

    def worker() -> None:
        with Session(pg_engine) as session:
            barrier.wait(timeout=10)
            results.append(
                skus_module.adjust_sku_stock(
                    sku_id,
                    SKUAdjust(delta=-1, source="ml_sale"),
                    session,
                    "tenant-1",
                )
            )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert len(results) == 2
    assert sorted(result.previous_quantity for result in results) == [0, 1]
    assert sorted(result.new_quantity for result in results) == [0, 0]
    # Only the first transition actually removed a unit.
    assert sorted(result.clamped for result in results) == [False, True]
    deducted = [
        result.previous_quantity - result.new_quantity for result in results
    ]
    assert sorted(deducted) == [0, 1]

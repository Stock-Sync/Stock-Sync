"""
Configuração do pytest para catalog-service.
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.db.session import get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    def override_get_session():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

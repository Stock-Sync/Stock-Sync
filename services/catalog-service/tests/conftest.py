import pytest
from app.api.deps import get_tenant_id
from app.db.session import get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session, SQLModel


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

    def override_get_tenant_id():
        return "test-tenant"

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_tenant_id] = override_get_tenant_id
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(
    settings.sqlalchemy_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
)


def get_session():
    with Session(engine) as session:
        yield session

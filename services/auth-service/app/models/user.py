from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=255, unique=True, index=True)
    password_hash: str = Field(min_length=1)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)})
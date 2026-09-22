from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class SyncEventCreate(SQLModel):
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)


class SyncEventUpdate(SQLModel):
    status: str | None = Field(default=None, max_length=20)
    retry_count: int | None = Field(default=None, ge=0)
    error_message: str | None = Field(default=None, max_length=2000)
    processed_at: datetime | None = Field(default=None)


class SyncEventRead(SQLModel):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    event_type: str
    payload: dict
    status: str
    retry_count: int
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None

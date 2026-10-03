from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class ProductBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProductRead(ProductBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    user_id: UUID
    created_at: datetime
    updated_at: datetime

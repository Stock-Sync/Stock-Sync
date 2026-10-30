from datetime import datetime

from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelConfig


class ProductBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pictures: list[str] = Field(default_factory=list)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pictures: list[str] | None = None


class ProductRead(ProductBase):
    model_config = SQLModelConfig(from_attributes=True)

    id: int
    tenant_id: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import SKU, Product
from app.schemas import SKUCreate, SKURead, SKUUpdate

router = APIRouter(prefix="/skus", tags=["skus"])


@router.get("", response_model=list[SKURead])
def list_skus(session: Session = Depends(get_session)) -> list[SKU]:
    return list(session.exec(select(SKU)).all())


@router.post("", response_model=SKURead, status_code=201)
def create_sku(payload: SKUCreate, session: Session = Depends(get_session)) -> SKU:
    if session.get(Product, payload.product_id) is None:
        raise NotFoundError("Product")
    sku = SKU(**payload.model_dump())
    session.add(sku)
    session.commit()
    session.refresh(sku)
    return sku


@router.get("/{sku_id}", response_model=SKURead)
def get_sku(sku_id: int, session: Session = Depends(get_session)) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise NotFoundError("SKU")
    return sku


@router.put("/{sku_id}", response_model=SKURead)
def update_sku(
    sku_id: int,
    payload: SKUUpdate,
    session: Session = Depends(get_session),
) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise NotFoundError("SKU")
    data = payload.model_dump(exclude_unset=True)
    if "product_id" in data and data["product_id"] is not None:
        if session.get(Product, data["product_id"]) is None:
            raise NotFoundError("Product")
    for key, value in data.items():
        setattr(sku, key, value)
    session.add(sku)
    session.commit()
    session.refresh(sku)
    return sku


@router.delete("/{sku_id}", status_code=204)
def delete_sku(sku_id: int, session: Session = Depends(get_session)) -> None:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise NotFoundError("SKU")
    session.delete(sku)
    session.commit()

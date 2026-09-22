from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import Product
from app.schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter()


@router.get("", response_model=list[ProductRead])
def list_products(session: Session = Depends(get_session)) -> list[Product]:
    return list(session.exec(select(Product)).all())


@router.post("", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, session: Session = Depends(get_session)) -> Product:
    product = Product(**payload.model_dump())
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product")
    return product


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: Session = Depends(get_session),
) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, session: Session = Depends(get_session)) -> None:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product")
    session.delete(product)
    session.commit()

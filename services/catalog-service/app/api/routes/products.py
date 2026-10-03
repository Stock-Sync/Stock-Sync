from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import Product, SKU
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


# ── Lookup endpoints for sync-service integration ──

@router.get("/by-sku")
def get_product_by_sku(
    user_id: str,
    sku: str,
    session: Session = Depends(get_session),
):
    """
    Get product by SKU for a specific tenant.
    Used by sync-service to find product from internal SKU.
    """
    from uuid import UUID
    user_uuid = UUID(user_id)
    
    # Join Product -> SKU to find by internal_sku
    statement = (
        select(Product)
        .join(SKU, Product.id == SKU.product_id)
        .where(SKU.user_id == user_uuid)
        .where(SKU.internal_sku == sku)
    )
    product = session.exec(statement).first()
    
    if not product:
        raise NotFoundError("Product")
    
    # Get the SKU info for response
    sku_obj = session.exec(
        select(SKU).where(SKU.product_id == product.id).where(SKU.internal_sku == sku)
    ).first()
    
    return {
        "id": str(product.id),
        "user_id": str(product.user_id),
        "name": product.name,
        "description": product.description,
        "sku": sku_obj.internal_sku if sku_obj else sku,
        "price": sku_obj.price if sku_obj else None,
        "stock_quantity": sku_obj.stock_quantity if sku_obj else 0,
        "is_active": True,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


@router.get("/stock/{user_id}/{sku}")
def get_stock_quantity(
    user_id: str,
    sku: str,
    session: Session = Depends(get_session),
):
    """Get current stock quantity for a SKU."""
    from uuid import UUID
    user_uuid = UUID(user_id)
    
    sku_obj = session.exec(
        select(SKU).where(SKU.user_id == user_uuid).where(SKU.internal_sku == sku)
    ).first()
    
    if not sku_obj:
        raise NotFoundError("SKU")
    
    return {"quantity": sku_obj.stock_quantity}

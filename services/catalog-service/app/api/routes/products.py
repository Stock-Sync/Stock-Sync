from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.product import Product

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/by-sku")
def get_product_by_sku(
    user_id: str = Query(..., description="Tenant UUID"),
    sku: str = Query(..., description="Product SKU"),
    db: Session = Depends(get_session),
):
    """Get product by SKU for a specific tenant."""
    product = db.query(Product).filter(
        Product.user_id == user_id,
        Product.sku == sku
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {
        "id": str(product.id),
        "user_id": product.user_id,
        "sku": product.sku,
        "name": product.name,
        "description": None,
        "price": product.price,
        "is_active": True,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


@router.get("/stock/{user_id}/{sku}")
def get_stock_quantity(
    user_id: str,
    sku: str,
    db: Session = Depends(get_session),
):
    """Get current stock quantity for a SKU."""
    product = db.query(Product).filter(
        Product.user_id == user_id,
        Product.sku == sku
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"quantity": product.stock_quantity}
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.api.deps import get_tenant_id
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import SKU, PlatformMapping, Product
from app.schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter()


def _get_product_or_404(
    session: Session,
    product_id: int,
    tenant_id: str,
    include_deleted: bool = False,
) -> Product:
    product = session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise NotFoundError("Product")
    if not include_deleted and product.is_deleted:
        raise NotFoundError("Product")
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> list[Product]:
    statement = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.is_deleted.is_(False),
    )
    return list(session.exec(statement).all())


@router.post("", response_model=ProductRead, status_code=201)
def create_product(
    payload: ProductCreate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    product = Product(**payload.model_dump(), tenant_id=tenant_id)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    return _get_product_or_404(session, product_id, tenant_id)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> Product:
    product = _get_product_or_404(session, product_id, tenant_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: str = Depends(get_tenant_id),
) -> None:
    """Soft delete the product, its SKUs and their marketplace mappings."""
    now = datetime.now(UTC)
    product = _get_product_or_404(session, product_id, tenant_id)

    product.is_deleted = True
    product.updated_at = now
    session.add(product)

    skus = session.exec(
        select(SKU).where(SKU.product_id == product_id, SKU.tenant_id == tenant_id)
    ).all()

    sku_ids: list[int] = []
    for sku in skus:
        sku.is_deleted = True
        sku.updated_at = now
        session.add(sku)
        if sku.id is not None:
            sku_ids.append(sku.id)

    if sku_ids:
        mappings = session.exec(
            select(PlatformMapping).where(
                PlatformMapping.sku_id.in_(sku_ids),
                PlatformMapping.tenant_id == tenant_id,
            )
        ).all()
        for mapping in mappings:
            mapping.is_active = False
            mapping.updated_at = now
            session.add(mapping)

    session.commit()

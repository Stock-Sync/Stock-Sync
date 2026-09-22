from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import SKU, PlatformMapping
from app.schemas import PlatformMappingCreate, PlatformMappingRead

router = APIRouter()


@router.get("", response_model=list[PlatformMappingRead])
def list_platform_mappings(
    session: Session = Depends(get_session),
) -> list[PlatformMapping]:
    return list(session.exec(select(PlatformMapping)).all())


@router.post("", response_model=PlatformMappingRead, status_code=201)
def create_platform_mapping(
    payload: PlatformMappingCreate,
    session: Session = Depends(get_session),
) -> PlatformMapping:
    if session.get(SKU, payload.sku_id) is None:
        raise NotFoundError("SKU")
    mapping = PlatformMapping(**payload.model_dump())
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=PlatformMappingRead)
def get_platform_mapping(
    mapping_id: int, session: Session = Depends(get_session)
) -> PlatformMapping:
    mapping = session.get(PlatformMapping, mapping_id)
    if mapping is None:
        raise NotFoundError("PlatformMapping")
    return mapping

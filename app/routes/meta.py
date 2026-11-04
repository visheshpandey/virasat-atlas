"""Filter facets and totals for the sidebar."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.heritage import MetaOut
from app.services import site_service

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaOut)
async def meta(db: AsyncSession = Depends(get_db)) -> MetaOut:
    """Available site types, eras, themes and entry languages, with counts."""
    return await site_service.get_meta(db)

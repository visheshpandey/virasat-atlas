"""Filter facets and totals for the sidebar."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.heritage import MetaOut
from app.services import site_service

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaOut)
async def meta(
    state: str | None = Query(default=None, max_length=60),
    db: AsyncSession = Depends(get_db),
) -> MetaOut:
    """Available site types, eras, themes, languages and states, with counts.

    Pass `state` to scope the counts to one state; `states` still lists all of them.
    """
    return await site_service.get_meta(db, state)

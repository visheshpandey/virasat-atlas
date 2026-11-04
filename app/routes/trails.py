"""Heritage trail planning."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.site import Site
from app.schemas.heritage import THEMES, TrailRequest, TrailResponse
from app.services.site_service import has_theme
from app.services.trails import TrailError, TrailSite, build_trail

router = APIRouter(tags=["trails"])


@router.post("/trails", response_model=TrailResponse)
async def plan_trail(
    data: TrailRequest, db: AsyncSession = Depends(get_db)
) -> TrailResponse:
    """Order a set of sites into a short visiting route.

    With site_ids the given sites are used as they are. Otherwise sites are taken
    from the theme (or all sites) and a geographic cluster is chosen.
    """
    use_all = bool(data.site_ids)
    if use_all:
        wanted = set(data.site_ids)
        sites = (await db.execute(select(Site).where(Site.id.in_(wanted)))).scalars().all()
        missing = wanted - {s.id for s in sites}
        if missing:
            raise HTTPException(status_code=404, detail="Some site_ids were not found")
    else:
        if data.theme and data.theme not in THEMES:
            raise HTTPException(
                status_code=422, detail=f"theme must be one of: {', '.join(THEMES)}"
            )
        sites = (await db.execute(select(Site))).scalars().all()
        if data.theme:
            sites = [s for s in sites if has_theme(s, data.theme)]

    start = (
        (data.start_lat, data.start_lng) if data.start_lat is not None else None
    )
    try:
        result = build_trail(
            [TrailSite(str(s.id), s.name, s.site_type, s.lat, s.lng) for s in sites],
            start=start,
            max_stops=data.max_stops,
            use_all=use_all,
        )
    except TrailError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return TrailResponse(**result)

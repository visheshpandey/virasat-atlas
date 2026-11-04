"""Site queries: listing, filters, proximity, creation and facet counts.

Proximity uses PostGIS ST_DWithin when DATABASE_URL is PostgreSQL and a Haversine
scan in Python otherwise (SQLite). Both return distances in metres.
"""
import uuid
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entry import Entry
from app.models.site import Site
from app.schemas.heritage import (
    THEMES,
    FacetCount,
    MetaOut,
    NearbyList,
    NearbySite,
    SiteCreate,
    SiteDetail,
    SiteList,
    SiteOut,
)
from app.services.entry_service import entry_out
from app.services.search_index import rebuild_from_db
from app.utils.geo import haversine
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def reindex(db: AsyncSession) -> None:
    """Rebuild the search index after a write. A failure is logged, never raised."""
    try:
        await rebuild_from_db(db)
    except Exception as exc:  # the write already succeeded; search can catch up later
        logger.error(f"search_reindex_failed: {exc}", exc_info=exc)


def has_theme(site: Site, theme: str) -> bool:
    """True if the site carries the theme. The "unesco" theme also matches the flag."""
    return theme in (site.themes or []) or (theme == "unesco" and site.unesco)


async def entry_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    """Number of field entries per site id."""
    rows = await db.execute(
        select(Entry.site_id, func.count(Entry.id))
        .where(Entry.site_id.is_not(None))
        .group_by(Entry.site_id)
    )
    return {site_id: n for site_id, n in rows.all()}


def site_out(site: Site, count: int = 0) -> SiteOut:
    out = SiteOut.model_validate(site)
    out.entry_count = count
    return out


async def list_sites(
    db: AsyncSession,
    site_type: str | None,
    era: str | None,
    theme: str | None,
    unesco: bool | None,
) -> SiteList:
    """All sites matching the optional filters, ordered by name."""
    stmt = select(Site).order_by(Site.name)
    if site_type:
        stmt = stmt.where(Site.site_type == site_type)
    if era:
        stmt = stmt.where(func.lower(Site.era) == era.lower())
    if unesco is not None:
        stmt = stmt.where(Site.unesco == unesco)
    sites = (await db.execute(stmt)).scalars().all()
    if theme:  # JSON array membership is portable only when done in Python
        sites = [s for s in sites if has_theme(s, theme)]
    counts = await entry_counts(db)
    items = [site_out(s, counts.get(s.id, 0)) for s in sites]
    return SiteList(items=items, total=len(items))


async def get_site_detail(db: AsyncSession, site_id: uuid.UUID) -> SiteDetail:
    """One site with its field entries, newest first. 404 if unknown."""
    site = await db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    entries = (
        await db.execute(
            select(Entry).where(Entry.site_id == site_id).order_by(Entry.created_at.desc())
        )
    ).scalars().all()
    base = site_out(site, len(entries))
    return SiteDetail(**base.model_dump(), entries=[entry_out(e) for e in entries])


async def sites_within(
    db: AsyncSession, lat: float, lng: float, radius_m: float
) -> list[tuple[Site, float]]:
    """Sites within radius_m of a point, as (site, distance_m), nearest first."""
    if settings.is_postgres:
        rows = (
            await db.execute(
                text(
                    "SELECT s.id, ST_Distance(s.geog, q.p) AS d "
                    "FROM sites s, (SELECT ST_SetSRID(ST_MakePoint("
                    "CAST(:lng AS double precision), CAST(:lat AS double precision)), 4326)"
                    "::geography AS p) q "
                    "WHERE ST_DWithin(s.geog, q.p, CAST(:r AS double precision)) ORDER BY d"
                ),
                {"lat": lat, "lng": lng, "r": radius_m},
            )
        ).all()
        if not rows:
            return []
        by_id = {
            s.id: s
            for s in (
                await db.execute(select(Site).where(Site.id.in_([r[0] for r in rows])))
            ).scalars()
        }
        return [(by_id[r[0]], float(r[1])) for r in rows if r[0] in by_id]

    found = []
    for site in (await db.execute(select(Site))).scalars():
        dist = haversine(lat, lng, site.lat, site.lng)
        if dist <= radius_m:
            found.append((site, dist))
    found.sort(key=lambda pair: pair[1])
    return found


async def nearby_sites(db: AsyncSession, lat: float, lng: float, radius_km: float) -> NearbyList:
    """Sites within radius_km of a point, nearest first."""
    hits = await sites_within(db, lat, lng, radius_km * 1000)
    counts = await entry_counts(db)
    items = [
        NearbySite(
            **site_out(s, counts.get(s.id, 0)).model_dump(),
            distance_km=round(dist / 1000, 3),
        )
        for s, dist in hits
    ]
    return NearbyList(items=items, total=len(items), radius_km=radius_km)


async def nearest_site(
    db: AsyncSession, lat: float, lng: float, max_km: float
) -> Site | None:
    """The closest site within max_km, or None."""
    hits = await sites_within(db, lat, lng, max_km * 1000)
    return hits[0][0] if hits else None


async def create_site(db: AsyncSession, data: SiteCreate) -> SiteOut:
    """Persist a new site and refresh the search index."""
    unknown = [t for t in data.themes if t not in THEMES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown themes: {', '.join(unknown)}")
    site = Site(**data.model_dump())
    db.add(site)
    await db.commit()
    await db.refresh(site)
    logger.info(f"site_created id={site.id} type={site.site_type}")
    await reindex(db)
    return site_out(site, 0)


async def get_meta(db: AsyncSession) -> MetaOut:
    """Available filter values with counts. Types, eras and themes count sites."""
    sites = (await db.execute(select(Site))).scalars().all()
    languages = Counter(
        (await db.execute(select(Entry.language))).scalars().all()
    )
    entry_total = sum(languages.values())

    def facet(counter: Counter) -> list[FacetCount]:
        ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        return [FacetCount(value=v, count=n) for v, n in ordered]

    themes: Counter = Counter()
    for s in sites:
        themes.update(set(s.themes or []) | ({"unesco"} if s.unesco else set()))
    return MetaOut(
        types=facet(Counter(s.site_type for s in sites)),
        eras=facet(Counter(s.era for s in sites if s.era)),
        themes=facet(themes),
        languages=facet(languages),
        sites=len(sites),
        entries=entry_total,
    )

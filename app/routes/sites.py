"""Heritage site endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.heritage import (
    NearbyList,
    SiteCreate,
    SiteDetail,
    SiteImage,
    SiteList,
    SiteOut,
    SiteType,
)
from app.services import site_images, site_service

router = APIRouter(prefix="/sites", tags=["sites"])

_optional_bearer = HTTPBearer(auto_error=False)


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user, but a missing header is 401 rather than the framework's 403."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await get_current_user(credentials, db)


@router.get("", response_model=SiteList)
async def list_sites(
    site_type: SiteType | None = Query(default=None, alias="type"),
    era: str | None = Query(default=None, max_length=50),
    theme: str | None = Query(default=None, max_length=50),
    unesco: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> SiteList:
    """List sites, optionally filtered by type, era, theme and UNESCO status."""
    return await site_service.list_sites(db, site_type, era, theme, unesco)


# Declared before /{site_id} so "nearby" is never read as an id.
@router.get("/nearby", response_model=NearbyList)
async def nearby_sites(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=500),
    db: AsyncSession = Depends(get_db),
) -> NearbyList:
    """Sites within radius_km of a point, nearest first."""
    return await site_service.nearby_sites(db, lat, lng, radius_km)


@router.get("/{site_id}", response_model=SiteDetail)
async def get_site(site_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SiteDetail:
    """One site with its field entries."""
    return await site_service.get_site_detail(db, site_id)


@router.get("/{site_id}/image", response_model=SiteImage)
async def get_site_image(site_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SiteImage:
    """A representative photo for the site, looked up server-side. Empty fields if none found."""
    site = await site_service.get_site_detail(db, site_id)  # 404 if the site does not exist
    return SiteImage(**(await site_images.get_site_image(site.name) or {}))


@router.post("", response_model=SiteOut, status_code=201)
async def create_site(
    data: SiteCreate,
    _: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SiteOut:
    """Add a site. Requires a bearer token."""
    return await site_service.create_site(db, data)

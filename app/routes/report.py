from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.report import ReportCreate, ReportOut, NearbyReportsResponse
from app.routes.deps import get_current_user
from app.services.report_service import create_report, get_nearby_reports

router = APIRouter(prefix="/report", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def submit_report(
    data: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_report(data, current_user, db)


@router.get("/nearby", response_model=NearbyReportsResponse)
async def nearby_reports(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_meters: int = Query(default=500, ge=1, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_nearby_reports(lat, lng, radius_meters, limit, db)

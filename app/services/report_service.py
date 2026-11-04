import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.safety_report import SafetyReport
from app.models.user import User
from app.schemas.report import ReportCreate, ReportOut, NearbyReportItem, NearbyReportsResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def create_report(data: ReportCreate, user: User, db: AsyncSession) -> ReportOut:
    report = SafetyReport(
        user_id=user.id,
        latitude=data.latitude,
        longitude=data.longitude,
        report_type=data.report_type.value,
        description=data.description,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    logger.info(f"report_submitted user={user.id} type={data.report_type}")
    return ReportOut.model_validate(report)


async def get_nearby_reports(
    lat: float,
    lng: float,
    radius_meters: int,
    limit: int,
    db: AsyncSession,
) -> NearbyReportsResponse:
    from sqlalchemy import func
    from geoalchemy2 import Geography

    target_point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326).cast(Geography)
    distance_col = func.ST_Distance(SafetyReport.geog, target_point).label('distance')

    query = (
        select(SafetyReport, distance_col)
        .where(func.ST_DWithin(SafetyReport.geog, target_point, radius_meters))
        .order_by(distance_col)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    nearby = []
    for r, dist in rows:
        nearby.append(
            NearbyReportItem(
                id=r.id,
                latitude=r.latitude,
                longitude=r.longitude,
                report_type=r.report_type,
                distance_meters=round(dist, 2),
                created_at=r.created_at,
            )
        )

    return NearbyReportsResponse(reports=nearby, total=len(nearby), radius_meters=radius_meters)

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.safety_report import SafetyReport
from app.utils.risk import time_risk_modifier, crowd_risk_modifier, lighting_modifier, crime_zone_modifier
from app.utils.geo import haversine


async def compute_safety_score(
    lat: float,
    lng: float,
    db: AsyncSession,
    ts: datetime | None = None,
) -> tuple[float, dict]:
    """
    Compute composite safety score [0,1] for a geographic point.
    Returns (score, risk_factors_dict).
    """
    if ts is None:
        ts = datetime.now(timezone.utc)

    # Sub-scores
    crime_index = crime_zone_modifier(lat, lng, ts)
    lighting_score = lighting_modifier(lat, lng, ts)
    crowd_risk = crowd_risk_modifier(lat, lng, ts)
    time_mod = time_risk_modifier(ts)

    # Report density within 100m
    report_count = await _count_nearby_reports(lat, lng, 100.0, db)
    report_density = min(report_count / 10.0, 1.0)

    raw_score = (
        (1 - crime_index) * 0.30
        + lighting_score * 0.25
        + (1 - crowd_risk) * 0.20
        + (1 - report_density) * 0.15
        + (1 - time_mod) * 0.10
    )
    safety_score = max(0.0, min(1.0, raw_score))

    risk_factors = {
        "crime_index": round(crime_index, 4),
        "lighting_score": round(lighting_score, 4),
        "time_modifier": round(time_mod, 4),
        "crowd_density": round(crowd_risk, 4),
        "report_density": round(report_density, 4),
    }
    return round(safety_score, 4), risk_factors


async def _count_nearby_reports(lat: float, lng: float, radius_m: float, db: AsyncSession) -> int:
    """Count safety reports within radius_m meters of (lat, lng)."""
    from sqlalchemy import func
    from geoalchemy2 import Geography

    target_point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326).cast(Geography)

    result = await db.execute(
        select(func.count()).select_from(SafetyReport).where(
            func.ST_DWithin(SafetyReport.geog, target_point, radius_m)
        )
    )
    return result.scalar() or 0

import uuid
from datetime import datetime, timezone

from app.models.user import User
from app.schemas.sos import SOSRequest, SOSResponse, SafePoint
from app.utils.geo import haversine
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Simulated safe points for Indore city center
SAFE_POINTS = [
    {"name": "Indore Central Police Station", "latitude": 22.7180, "longitude": 75.8560},
    {"name": "MY Hospital", "latitude": 22.7220, "longitude": 75.8640},
    {"name": "Rajwada Police Chowki", "latitude": 22.7195, "longitude": 75.8580},
    {"name": "Indore Railway Station", "latitude": 22.7200, "longitude": 75.7850},
    {"name": "Bombay Hospital", "latitude": 22.7310, "longitude": 75.8870},
]


async def trigger_sos(data: SOSRequest, user: User) -> SOSResponse:
    alert_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)

    # Find nearest safe points
    points_with_dist = [
        SafePoint(
            name=sp["name"],
            latitude=sp["latitude"],
            longitude=sp["longitude"],
            distance_meters=round(haversine(data.latitude, data.longitude, sp["latitude"], sp["longitude"]), 1),
        )
        for sp in SAFE_POINTS
    ]
    points_with_dist.sort(key=lambda p: p.distance_meters)
    nearest = points_with_dist[:3]

    logger.warning(
        f"sos_triggered alert_id={alert_id} user={user.id} lat={data.latitude} lng={data.longitude}"
    )

    return SOSResponse(
        alert_id=alert_id,
        status="DISPATCHED",
        timestamp=ts,
        location={"latitude": data.latitude, "longitude": data.longitude},
        message="Emergency services have been notified. Stay calm and move to a public area.",
        nearest_safe_points=nearest,
    )

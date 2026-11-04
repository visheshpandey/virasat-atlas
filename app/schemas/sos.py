import uuid
from datetime import datetime
from pydantic import BaseModel


class SOSRequest(BaseModel):
    latitude: float
    longitude: float
    message: str | None = None


class SafePoint(BaseModel):
    name: str
    latitude: float
    longitude: float
    distance_meters: float


class SOSResponse(BaseModel):
    alert_id: uuid.UUID
    status: str
    timestamp: datetime
    location: dict
    message: str
    nearest_safe_points: list[SafePoint]

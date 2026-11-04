import uuid
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class ReportType(str, Enum):
    HARASSMENT = "HARASSMENT"
    ASSAULT = "ASSAULT"
    POOR_LIGHTING = "POOR_LIGHTING"
    UNSAFE_CROWD = "UNSAFE_CROWD"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    OTHER = "OTHER"


class ReportCreate(BaseModel):
    latitude: float
    longitude: float
    report_type: ReportType
    description: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    latitude: float
    longitude: float
    report_type: ReportType
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NearbyReportItem(BaseModel):
    id: uuid.UUID
    latitude: float
    longitude: float
    report_type: ReportType
    distance_meters: float
    created_at: datetime

    model_config = {"from_attributes": True}


class NearbyReportsResponse(BaseModel):
    reports: list[NearbyReportItem]
    total: int
    radius_meters: int

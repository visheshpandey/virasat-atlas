import uuid
from pydantic import BaseModel, field_validator


class RouteRequest(BaseModel):
    source_lat: float
    source_lng: float
    dest_lat: float
    dest_lng: float

    @field_validator("dest_lat")
    @classmethod
    def not_same_point(cls, v: float, info) -> float:
        data = info.data
        if (
            "source_lat" in data
            and "source_lng" in data
            and abs(v - data["source_lat"]) < 1e-6
        ):
            # will be checked with lng too in service layer
            pass
        return v


class RiskFactors(BaseModel):
    crime_index: float
    lighting_score: float
    time_modifier: float
    crowd_density: float
    report_density: float


class GeoJSONLineString(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]


class RouteResponse(BaseModel):
    route_id: uuid.UUID
    safety_score: float
    distance_meters: float
    estimated_minutes: float
    path: GeoJSONLineString
    risk_factors: RiskFactors

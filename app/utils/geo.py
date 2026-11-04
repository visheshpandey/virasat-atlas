import math

EARTH_RADIUS_M = 6_371_000.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in meters between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lng, max_lat, max_lng) for a circle."""
    delta_lat = math.degrees(radius_m / EARTH_RADIUS_M)
    delta_lng = math.degrees(radius_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lat - delta_lat, lng - delta_lng, lat + delta_lat, lng + delta_lng

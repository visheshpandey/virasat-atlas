from datetime import datetime


def time_risk_modifier(ts: datetime) -> float:
    """Return risk modifier [0,1] based on hour of day."""
    hour = ts.hour
    if 6 <= hour < 9:
        return 0.10
    elif 9 <= hour < 18:
        return 0.05
    elif 18 <= hour < 21:
        return 0.20
    elif 21 <= hour < 24:
        return 0.50
    else:  # 00:00 – 06:00
        return 0.70


def crowd_risk_modifier(lat: float, lng: float, ts: datetime) -> float:
    """Simulated crowd density risk. Replace with real data source."""
    hour = ts.hour
    # Simulate higher crowd risk in late evening
    if 20 <= hour < 23:
        return 0.60
    elif 23 <= hour or hour < 5:
        return 0.30  # low crowd = less protection
    return 0.20


def lighting_modifier(lat: float, lng: float, ts: datetime) -> float:
    """Simulated lighting score [0=dark, 1=bright]. Proxy from time of day."""
    hour = ts.hour
    if 6 <= hour < 20:
        return 0.90  # daytime
    elif 20 <= hour < 22:
        return 0.60
    else:
        return 0.30  # night


def crime_zone_modifier(lat: float, lng: float, ts: datetime) -> float:
    """
    Simulated static crime heat map for Indore city center.
    Returns crime index [0,1]. Replace with real crime API.
    """
    # Simulate a few high-crime zones by coordinate proximity
    HIGH_CRIME_ZONES = [
        (22.7150, 75.8500),
        (22.7300, 75.8700),
        (22.7100, 75.8650),
    ]
    from app.utils.geo import haversine
    for zlat, zlng in HIGH_CRIME_ZONES:
        if haversine(lat, lng, zlat, zlng) < 300:
            return 0.75
    return 0.15

"""Heritage trail planner. Not yet implemented."""
from dataclasses import dataclass


class TrailError(ValueError):
    """Raised when no valid trail exists. Routes turn this into a 422."""


@dataclass
class TrailSite:
    id: str
    name: str
    site_type: str
    lat: float
    lng: float


def build_trail(
    sites: list[TrailSite],
    start: tuple[float, float] | None = None,
    max_stops: int = 8,
    use_all: bool = False,
) -> dict:
    """Return a TrailResponse-shaped dict.

    use_all=True (explicit site_ids) skips clustering and keeps every site.
    Otherwise picks a cluster within 150 km, nearest the start or else the densest.
    Raises TrailError if fewer than 2 sites are available.
    """
    raise NotImplementedError

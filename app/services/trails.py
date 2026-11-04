"""Heritage trail planner.

Picks a geographic cluster of sites, orders the stops with nearest-neighbour followed by
2-opt, and reports straight-line leg distances. Distances are not road distances.
"""
from dataclasses import dataclass

from app.utils.geo import haversine

CLUSTER_RADIUS_KM = 150.0
SPEED_KMH = 45.0
HOURS_PER_STOP = 1.0
_ALL_STARTS_LIMIT = 30  # try nearest-neighbour from every site only for small trails

Point = tuple[float, float]  # (lat, lng)


class TrailError(ValueError):
    """Raised when no valid trail exists. Routes turn this into a 422."""


@dataclass
class TrailSite:
    id: str
    name: str
    site_type: str
    lat: float
    lng: float


def _km(a: Point, b: Point) -> float:
    return haversine(a[0], a[1], b[0], b[1]) / 1000.0


def _select_cluster(sites: list[TrailSite], start: Point | None, max_stops: int) -> list[TrailSite]:
    """Choose up to max_stops sites that lie close together.

    With a start, the cluster is centred on the site nearest the start. Without one, it is
    centred on the site with the most neighbours inside CLUSTER_RADIUS_KM.
    """
    ordered = sorted(sites, key=lambda s: (s.name, s.id))  # deterministic ties
    if start is not None:
        seed = min(ordered, key=lambda s: _km(start, (s.lat, s.lng)))
    else:
        def density(s: TrailSite) -> tuple[int, float]:
            near = [_km((s.lat, s.lng), (o.lat, o.lng)) for o in ordered]
            inside = [d for d in near if d <= CLUSTER_RADIUS_KM]
            return len(inside), -sum(inside)

        seed = max(ordered, key=density)

    by_distance = sorted(ordered, key=lambda s: _km((seed.lat, seed.lng), (s.lat, s.lng)))
    cluster = [s for s in by_distance if _km((seed.lat, seed.lng), (s.lat, s.lng)) <= CLUSTER_RADIUS_KM]
    if len(cluster) < 2:  # isolated seed: fall back to its nearest neighbours at any distance
        cluster = by_distance
    return cluster[:max_stops]


def _path_length(path: list[int], dist: list[list[float]]) -> float:
    return sum(dist[path[i]][path[i + 1]] for i in range(len(path) - 1))


def _nearest_neighbour(first: int, nodes: list[int], dist: list[list[float]]) -> list[int]:
    path = [first]
    remaining = set(nodes) - {first}
    while remaining:
        last = path[-1]
        nxt = min(remaining, key=lambda n: (dist[last][n], n))
        path.append(nxt)
        remaining.remove(nxt)
    return path


def _two_opt(path: list[int], dist: list[list[float]], fixed_first: bool) -> list[int]:
    """Improve an open path by reversing segments while that shortens it."""
    path = path[:]
    n = len(path)
    lo = 1 if fixed_first else 0
    improved = True
    while improved:
        improved = False
        for i in range(lo, n - 1):
            for j in range(i + 1, n):
                a = path[i - 1] if i > 0 else None
                b, c = path[i], path[j]
                d = path[j + 1] if j + 1 < n else None
                old = (dist[a][b] if a is not None else 0.0) + (dist[c][d] if d is not None else 0.0)
                new = (dist[a][c] if a is not None else 0.0) + (dist[b][d] if d is not None else 0.0)
                if new < old - 1e-9:
                    path[i: j + 1] = reversed(path[i: j + 1])
                    improved = True
    return path


def _order(points: list[Point], start: Point | None) -> list[int]:
    """Return visiting order as indices into `points` (+1 offset handled internally)."""
    nodes = ([start] if start is not None else []) + points
    offset = 1 if start is not None else 0
    size = len(nodes)
    dist = [[_km(nodes[i], nodes[j]) for j in range(size)] for i in range(size)]
    free = list(range(offset, size))

    if start is not None:
        best = _two_opt(_nearest_neighbour(0, list(range(size)), dist), dist, fixed_first=True)
    else:
        starts = free if len(free) <= _ALL_STARTS_LIMIT else free[:1]
        candidates = [_two_opt(_nearest_neighbour(s, free, dist), dist, fixed_first=False) for s in starts]
        best = min(candidates, key=lambda p: _path_length(p, dist))
    return [i - offset for i in best if i >= offset]


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
    unique = list({s.id: s for s in sites}.values())
    if len(unique) < 2:
        raise TrailError("A trail needs at least two matching sites")

    chosen = unique if use_all else _select_cluster(unique, start, max(2, max_stops))
    points = [(s.lat, s.lng) for s in chosen]
    order = _order(points, start)
    stops = [chosen[i] for i in order]

    path_points = ([start] if start is not None else []) + [(s.lat, s.lng) for s in stops]
    legs = [round(_km(path_points[i], path_points[i + 1]), 2) for i in range(len(path_points) - 1)]
    total = round(sum(legs), 2)

    return {
        "stops": [
            {"order": n, "id": s.id, "name": s.name, "site_type": s.site_type, "lat": s.lat, "lng": s.lng}
            for n, s in enumerate(stops, start=1)
        ],
        "leg_km": legs,
        "total_km": total,
        "est_hours": round(total / SPEED_KMH + HOURS_PER_STOP * len(stops), 2),
        "polyline": [[lat, lng] for lat, lng in path_points],
    }

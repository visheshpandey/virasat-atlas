import uuid
import hashlib
import functools
from datetime import datetime, timezone
from typing import Optional

import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import Route
from app.schemas.route import RouteResponse, GeoJSONLineString, RiskFactors
from app.services.safety_service import compute_safety_score
from app.utils.graph import build_grid_graph, nearest_node
from app.utils.geo import haversine
from app.utils.logger import get_logger

logger = get_logger(__name__)

# LRU cache for graph objects keyed by bounding-box hash (max 50, TTL handled externally)
_graph_cache: dict = {}
_CACHE_MAX = 50


def _bbox_key(src_lat, src_lng, dst_lat, dst_lng) -> str:
    raw = f"{src_lat:.4f},{src_lng:.4f},{dst_lat:.4f},{dst_lng:.4f}"
    return hashlib.md5(raw.encode()).hexdigest()


async def compute_safest_route(
    src_lat: float,
    src_lng: float,
    dst_lat: float,
    dst_lng: float,
    user_id: Optional[uuid.UUID],
    db: AsyncSession,
) -> RouteResponse:
    if abs(src_lat - dst_lat) < 1e-6 and abs(src_lng - dst_lng) < 1e-6:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Source and destination are the same")

    G = await _get_or_build_graph(src_lat, src_lng, dst_lat, dst_lng, db, mode="safe")

    src_node = nearest_node(G, src_lat, src_lng)
    dst_node = nearest_node(G, dst_lat, dst_lng)

    try:
        path_nodes = nx.dijkstra_path(G, src_node, dst_node, weight="weight")
    except nx.NetworkXNoPath:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No routable path exists between the given coordinates")

    return await _build_response(path_nodes, src_lat, src_lng, dst_lat, dst_lng, user_id, db)


async def compute_shortest_route(
    src_lat: float,
    src_lng: float,
    dst_lat: float,
    dst_lng: float,
    user_id: Optional[uuid.UUID],
    db: AsyncSession,
) -> RouteResponse:
    if abs(src_lat - dst_lat) < 1e-6 and abs(src_lng - dst_lng) < 1e-6:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Source and destination are the same")

    G = await _get_or_build_graph(src_lat, src_lng, dst_lat, dst_lng, db, mode="short")

    src_node = nearest_node(G, src_lat, src_lng)
    dst_node = nearest_node(G, dst_lat, dst_lng)

    try:
        path_nodes = nx.dijkstra_path(G, src_node, dst_node, weight="distance")
    except nx.NetworkXNoPath:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No routable path exists between the given coordinates")

    return await _build_response(path_nodes, src_lat, src_lng, dst_lat, dst_lng, user_id, db)


async def _get_or_build_graph(
    src_lat, src_lng, dst_lat, dst_lng, db: AsyncSession, mode: str
) -> nx.DiGraph:
    key = _bbox_key(src_lat, src_lng, dst_lat, dst_lng) + mode
    if key in _graph_cache:
        return _graph_cache[key]

    G = build_grid_graph(src_lat, src_lng, dst_lat, dst_lng)

    if mode == "safe":
        ts = datetime.now(timezone.utc)
        for u, v, data in G.edges(data=True):
            mid_lat = (u[0] + v[0]) / 2
            mid_lng = (u[1] + v[1]) / 2
            score, _ = await compute_safety_score(mid_lat, mid_lng, db, ts)
            G[u][v]["weight"] = 1.0 - score  # lower safety → higher weight

    if len(_graph_cache) >= _CACHE_MAX:
        oldest = next(iter(_graph_cache))
        del _graph_cache[oldest]
    _graph_cache[key] = G
    return G


async def _build_response(
    path_nodes: list,
    src_lat, src_lng, dst_lat, dst_lng,
    user_id: Optional[uuid.UUID],
    db: AsyncSession,
) -> RouteResponse:
    ts = datetime.now(timezone.utc)

    # Compute total distance
    total_dist = sum(
        haversine(path_nodes[i][0], path_nodes[i][1], path_nodes[i + 1][0], path_nodes[i + 1][1])
        for i in range(len(path_nodes) - 1)
    )

    # Average safety score across midpoints
    scores = []
    all_risk: dict = {}
    for i in range(len(path_nodes) - 1):
        mid_lat = (path_nodes[i][0] + path_nodes[i + 1][0]) / 2
        mid_lng = (path_nodes[i][1] + path_nodes[i + 1][1]) / 2
        s, rf = await compute_safety_score(mid_lat, mid_lng, db, ts)
        scores.append(s)
        all_risk = rf  # use last segment's risk factors as representative

    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.5

    # GeoJSON: [lng, lat] order
    coordinates = [[node[1], node[0]] for node in path_nodes]
    path_geojson = {"type": "LineString", "coordinates": coordinates}

    # Persist route
    route = Route(
        user_id=user_id,
        source_lat=src_lat,
        source_lng=src_lng,
        dest_lat=dst_lat,
        dest_lng=dst_lng,
        safety_score=avg_score,
        path=path_geojson,
    )
    db.add(route)
    await db.commit()
    await db.refresh(route)

    estimated_minutes = round((total_dist / 1000) / 5 * 60, 1)  # 5 km/h walking

    logger.info(
        f"route_computed user={user_id} score={avg_score} dist={total_dist:.1f}m"
    )

    return RouteResponse(
        route_id=route.id,
        safety_score=avg_score,
        distance_meters=round(total_dist, 2),
        estimated_minutes=estimated_minutes,
        path=GeoJSONLineString(**path_geojson),
        risk_factors=RiskFactors(**all_risk),
    )

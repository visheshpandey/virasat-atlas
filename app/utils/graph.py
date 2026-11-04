import networkx as nx
from app.utils.geo import haversine


def build_grid_graph(
    src_lat: float,
    src_lng: float,
    dst_lat: float,
    dst_lng: float,
    steps: int = 10,
) -> nx.DiGraph:
    """
    Build a directed grid graph between source and destination.
    Nodes are (lat, lng) tuples. Edge weights default to Haversine distance.
    """
    G = nx.DiGraph()

    lat_min = min(src_lat, dst_lat)
    lat_max = max(src_lat, dst_lat)
    lng_min = min(src_lng, dst_lng)
    lng_max = max(src_lng, dst_lng)

    # Expand bounding box slightly
    pad_lat = (lat_max - lat_min) * 0.1 or 0.005
    pad_lng = (lng_max - lng_min) * 0.1 or 0.005
    lat_min -= pad_lat
    lat_max += pad_lat
    lng_min -= pad_lng
    lng_max += pad_lng

    lat_step = (lat_max - lat_min) / steps
    lng_step = (lng_max - lng_min) / steps

    nodes = []
    for i in range(steps + 1):
        for j in range(steps + 1):
            lat = lat_min + i * lat_step
            lng = lng_min + j * lng_step
            nodes.append((lat, lng))
            G.add_node((lat, lng))

    # Connect adjacent nodes (4-directional grid)
    for i in range(steps + 1):
        for j in range(steps + 1):
            cur = (lat_min + i * lat_step, lng_min + j * lng_step)
            neighbors = []
            if i < steps:
                neighbors.append((lat_min + (i + 1) * lat_step, lng_min + j * lng_step))
            if j < steps:
                neighbors.append((lat_min + i * lat_step, lng_min + (j + 1) * lng_step))
            if i > 0:
                neighbors.append((lat_min + (i - 1) * lat_step, lng_min + j * lng_step))
            if j > 0:
                neighbors.append((lat_min + i * lat_step, lng_min + (j - 1) * lng_step))
            for nb in neighbors:
                dist = haversine(cur[0], cur[1], nb[0], nb[1])
                G.add_edge(cur, nb, distance=dist, weight=dist)

    return G


def nearest_node(G: nx.DiGraph, lat: float, lng: float):
    """Return the graph node closest to (lat, lng)."""
    return min(G.nodes, key=lambda n: haversine(n[0], n[1], lat, lng))

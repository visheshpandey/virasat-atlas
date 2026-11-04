"""Tests for trail clustering, ordering and distances."""
import itertools

import pytest

from app.services.trails import CLUSTER_RADIUS_KM, TrailError, TrailSite, _km, build_trail


def site(i: str, lat: float, lng: float, name: str | None = None) -> TrailSite:
    return TrailSite(id=i, name=name or f"Site {i}", site_type="temple", lat=lat, lng=lng)


# Real-ish Gujarat coordinates.
AHMEDABAD = site("ahm", 23.0225, 72.5714, "Ahmedabad")
ADALAJ = site("ada", 23.1666, 72.5808, "Adalaj")
MODHERA = site("mod", 23.5835, 72.1330, "Modhera")
PATAN = site("pat", 23.8588, 72.1017, "Patan")
SIDDHPUR = site("sid", 23.9166, 72.3733, "Siddhpur")
BHUJ = site("bhu", 23.2420, 69.6669, "Bhuj")
NIRONA = site("nir", 23.4000, 69.5800, "Nirona")
NORTH_CLUSTER = [AHMEDABAD, ADALAJ, MODHERA, PATAN, SIDDHPUR]
KUTCH_CLUSTER = [BHUJ, NIRONA]


def total_of_order(stops, start=None) -> float:
    pts = ([start] if start else []) + [(s["lat"], s["lng"]) for s in stops]
    return sum(_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def test_response_shape_and_consistency():
    trail = build_trail(NORTH_CLUSTER, max_stops=5)
    assert [s["order"] for s in trail["stops"]] == [1, 2, 3, 4, 5]
    assert len(trail["leg_km"]) == 4  # no start: n-1 legs
    assert trail["total_km"] == pytest.approx(sum(trail["leg_km"]), abs=0.01)
    assert trail["est_hours"] == pytest.approx(trail["total_km"] / 45 + 5, abs=0.01)
    assert len(trail["polyline"]) == 5
    assert trail["polyline"][0] == [trail["stops"][0]["lat"], trail["stops"][0]["lng"]]


def test_order_is_shorter_than_input_order_and_near_optimal():
    trail = build_trail(NORTH_CLUSTER, max_stops=5)
    naive = sum(
        _km((a.lat, a.lng), (b.lat, b.lng)) for a, b in zip(NORTH_CLUSTER, NORTH_CLUSTER[1:])
    )
    assert trail["total_km"] <= naive + 0.01

    best = min(
        sum(_km((a.lat, a.lng), (b.lat, b.lng)) for a, b in zip(p, p[1:]))
        for p in itertools.permutations(NORTH_CLUSTER)
    )
    assert trail["total_km"] <= best * 1.05


def test_collinear_sites_are_visited_in_line_order():
    line = [site(str(i), 23.0, 72.0 + i * 0.1) for i in (3, 0, 4, 1, 2)]
    lngs = [s["lng"] for s in build_trail(line, max_stops=5)["stops"]]
    assert lngs == sorted(lngs) or lngs == sorted(lngs, reverse=True)


def test_start_anchors_the_route():
    start = (24.0, 72.4)  # next to Siddhpur
    trail = build_trail(NORTH_CLUSTER, start=start, max_stops=5)
    assert trail["stops"][0]["id"] == "sid"
    assert len(trail["leg_km"]) == 5  # start->first plus 4 legs
    assert trail["polyline"][0] == [24.0, 72.4]
    assert len(trail["polyline"]) == 6
    assert trail["leg_km"][0] == pytest.approx(_km(start, (SIDDHPUR.lat, SIDDHPUR.lng)), abs=0.01)
    assert trail["total_km"] == pytest.approx(total_of_order(trail["stops"], start), abs=0.05)


def test_start_in_kutch_picks_the_kutch_cluster():
    trail = build_trail(NORTH_CLUSTER + KUTCH_CLUSTER, start=(23.25, 69.65), max_stops=8)
    assert {s["id"] for s in trail["stops"]} == {"bhu", "nir"}


def test_no_start_picks_the_densest_cluster():
    trail = build_trail(NORTH_CLUSTER + KUTCH_CLUSTER, max_stops=8)
    ids = {s["id"] for s in trail["stops"]}
    assert ids <= {s.id for s in NORTH_CLUSTER}
    assert len(ids) >= 3


def test_cluster_stays_within_radius():
    trail = build_trail(NORTH_CLUSTER + KUTCH_CLUSTER, max_stops=8)
    pts = [(s["lat"], s["lng"]) for s in trail["stops"]]
    assert max(_km(a, b) for a in pts for b in pts) <= 2 * CLUSTER_RADIUS_KM


def test_max_stops_is_respected():
    trail = build_trail(NORTH_CLUSTER, max_stops=3)
    assert len(trail["stops"]) == 3


def test_explicit_sites_skip_clustering():
    trail = build_trail([AHMEDABAD, BHUJ], use_all=True)
    assert {s["id"] for s in trail["stops"]} == {"ahm", "bhu"}
    assert trail["total_km"] > CLUSTER_RADIUS_KM


def test_isolated_pair_still_makes_a_trail_without_explicit_ids():
    trail = build_trail([AHMEDABAD, BHUJ], max_stops=5)
    assert len(trail["stops"]) == 2


@pytest.mark.parametrize("sites", [[], [AHMEDABAD]])
def test_too_few_sites(sites):
    with pytest.raises(TrailError):
        build_trail(sites)


def test_duplicate_ids_count_once():
    with pytest.raises(TrailError):
        build_trail([AHMEDABAD, AHMEDABAD])


def test_deterministic():
    assert build_trail(NORTH_CLUSTER, max_stops=5) == build_trail(list(reversed(NORTH_CLUSTER)), max_stops=5)

"""Region (state) filter: meta facets, /sites, /search, and auto-filled state on ingest."""
import pytest

API = "/api/v1"
JAIPUR = {"name": "Hawa Mahal Test", "site_type": "palace", "lat": 26.9239, "lng": 75.8267,
          "description": "A pink sandstone facade with many small windows.", "state": "Rajasthan"}


@pytest.fixture(scope="module")
def jaipur_site(client, auth_headers):
    """One Rajasthan site, plus a Gujarat one so the two states can be told apart."""
    client.post(f"{API}/sites", headers=auth_headers, json={
        "name": "Region Test Stepwell", "site_type": "stepwell", "lat": 23.8589, "lng": 72.1017,
        "description": "A deep stepwell for region tests.", "state": "Gujarat"})
    resp = client.post(f"{API}/sites", headers=auth_headers, json=JAIPUR)
    assert resp.status_code == 201
    return resp.json()


def test_meta_lists_every_state_with_counts_and_slugs(client, jaipur_site):
    states = {s["value"]: s for s in client.get(f"{API}/meta").json()["states"]}
    assert states["Rajasthan"]["slug"] == "rajasthan" and states["Rajasthan"]["count"] >= 1
    assert "Gujarat" in states


def test_meta_scoped_to_a_state_keeps_the_full_states_list(client, jaipur_site):
    scoped = client.get(f"{API}/meta", params={"state": "rajasthan"}).json()
    assert scoped["sites"] == 1
    assert {t["value"] for t in scoped["types"]} == {"palace"}
    assert {s["value"] for s in scoped["states"]} >= {"Rajasthan", "Gujarat"}
    everything = client.get(f"{API}/meta", params={"state": "all"}).json()
    assert everything["sites"] > scoped["sites"]


def test_sites_state_filter_accepts_name_slug_and_all(client, jaipur_site):
    for value in ("Rajasthan", "rajasthan", "RAJASTHAN"):
        items = client.get(f"{API}/sites", params={"state": value}).json()["items"]
        assert [s["name"] for s in items] == ["Hawa Mahal Test"]
    total = client.get(f"{API}/sites").json()["total"]
    assert client.get(f"{API}/sites", params={"state": "all"}).json()["total"] == total


def test_multi_word_state_slug_matches(client, auth_headers):
    client.post(f"{API}/sites", headers=auth_headers, json={
        "name": "Khajuraho Test", "site_type": "temple", "lat": 24.85, "lng": 79.92,
        "state": "Madhya Pradesh"})
    items = client.get(f"{API}/sites", params={"state": "madhya-pradesh"}).json()["items"]
    assert [s["name"] for s in items] == ["Khajuraho Test"]


def test_search_is_scoped_by_state(client, jaipur_site):
    everywhere = client.get(f"{API}/search", params={"q": "stepwell"}).json()["results"]
    assert any(r["title"] == "Region Test Stepwell" for r in everywhere)
    in_raj = client.get(f"{API}/search", params={"q": "stepwell", "state": "rajasthan"}).json()["results"]
    assert all(r["title"] != "Region Test Stepwell" for r in in_raj)
    hawa = client.get(f"{API}/search", params={"q": "sandstone windows", "state": "rajasthan"}).json()["results"]
    assert hawa and hawa[0]["title"] == "Hawa Mahal Test"


def test_new_site_without_state_takes_the_nearest_sites_state(client, auth_headers, jaipur_site):
    resp = client.post(f"{API}/sites", headers=auth_headers, json={
        "name": "Amber Test", "site_type": "fort", "lat": 26.9855, "lng": 75.8513})
    assert resp.json()["state"] == "Rajasthan"


def test_entry_without_state_gets_nearest_sites_state_even_when_far(client, jaipur_site):
    # ~30 km from the Jaipur site: too far to attach (2 km) but the state is still filled.
    resp = client.post(f"{API}/entries", data={
        "title": "Roadside shrine", "body": "A small shrine on the highway.",
        "lat": "27.15", "lng": "75.9"})
    body = resp.json()
    assert resp.status_code == 201
    assert body["site_id"] is None and body["state"] == "Rajasthan"


def test_entry_attached_to_a_site_inherits_its_state(client, jaipur_site):
    resp = client.post(f"{API}/entries", data={
        "title": "Morning light", "body": "Sunrise on the facade.",
        "site_id": jaipur_site["id"]})
    assert resp.json()["state"] == "Rajasthan"


def test_explicit_entry_state_wins_and_entry_without_location_has_none(client, jaipur_site):
    explicit = client.post(f"{API}/entries", data={
        "title": "Override", "body": "x", "lat": "26.92", "lng": "75.82", "state": "Gujarat"}).json()
    assert explicit["state"] == "Gujarat"
    nowhere = client.post(f"{API}/entries", data={"title": "No place", "body": "x"}).json()
    assert nowhere["state"] is None


def test_scoped_meta_counts_entries_by_state(client, jaipur_site):
    scoped = client.get(f"{API}/meta", params={"state": "rajasthan"}).json()
    assert scoped["entries"] >= 2  # the roadside shrine and "Morning light"

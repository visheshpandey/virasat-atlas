"""API tests against a temporary SQLite database (see conftest.py)."""
import io

import pytest
from PIL import Image

from app.services import ocr_service

API = "/api/v1"

RANI_KI_VAV = {
    "name": "Rani ki Vav", "site_type": "stepwell", "era": "Chaulukya (Solanki)",
    "century": 11, "district": "Patan", "lat": 23.8593, "lng": 72.1017,
    "description": "Stepwell with seven levels of carved sculpture.",
    "themes": ["water-architecture", "stone-carving"], "unesco": True,
}
MODHERA = {
    "name": "Modhera Sun Temple", "site_type": "temple", "era": "Chaulukya (Solanki)",
    "century": 11, "district": "Mehsana", "lat": 23.5835, "lng": 72.1330,
    "description": "Sun temple with a stepped tank in front.",
    "themes": ["stone-carving", "pilgrimage"], "unesco": False,
}


def png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 60)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def sites(client, auth_headers) -> dict:
    """Two sites created once for the module, keyed by name."""
    created = {}
    for payload in (RANI_KI_VAV, MODHERA):
        res = client.post(f"{API}/sites", json=payload, headers=auth_headers)
        assert res.status_code == 201, res.text
        created[payload["name"]] = res.json()
    return created


# --- basics and error envelope ---
def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get(f"{API}/health").status_code == 200


def test_unknown_api_path_uses_error_envelope(client):
    res = client.get(f"{API}/sites/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_validation_error_is_clean_json(client):
    res = client.get(f"{API}/sites/nearby", params={"lat": 999, "lng": 72})
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"][0]["loc"][-1] == "lat"


# --- sites ---
def test_create_site_without_token_is_401(client):
    assert client.post(f"{API}/sites", json=RANI_KI_VAV).status_code == 401


def test_create_site_with_bad_token_is_401(client):
    res = client.post(
        f"{API}/sites", json=RANI_KI_VAV, headers={"Authorization": "Bearer nonsense"}
    )
    assert res.status_code == 401


def test_create_site_rejects_unknown_theme(client, auth_headers):
    res = client.post(
        f"{API}/sites", json={**MODHERA, "name": "X", "themes": ["not-a-theme"]},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_list_sites_and_filters(client, sites):
    everything = client.get(f"{API}/sites").json()
    assert everything["total"] == len(everything["items"]) >= 2

    stepwells = client.get(f"{API}/sites", params={"type": "stepwell"}).json()
    assert [s["name"] for s in stepwells["items"]] == ["Rani ki Vav"]

    unesco = client.get(f"{API}/sites", params={"unesco": "true"}).json()
    assert {s["name"] for s in unesco["items"]} == {"Rani ki Vav"}

    carved = client.get(f"{API}/sites", params={"theme": "stone-carving"}).json()
    assert {"Rani ki Vav", "Modhera Sun Temple"} <= {s["name"] for s in carved["items"]}

    era = client.get(f"{API}/sites", params={"era": "chaulukya (solanki)"}).json()
    assert era["total"] >= 2


def test_list_sites_rejects_unknown_type(client):
    assert client.get(f"{API}/sites", params={"type": "spaceship"}).status_code == 422


def test_nearby_sites_sorted_with_distance(client, sites):
    res = client.get(
        f"{API}/sites/nearby", params={"lat": 23.86, "lng": 72.10, "radius_km": 50}
    ).json()
    names = [s["name"] for s in res["items"]]
    assert names[0] == "Rani ki Vav"
    assert "Modhera Sun Temple" in names
    assert res["items"][0]["distance_km"] < res["items"][1]["distance_km"]
    assert res["items"][0]["distance_km"] < 1

    tight = client.get(
        f"{API}/sites/nearby", params={"lat": 23.86, "lng": 72.10, "radius_km": 5}
    ).json()
    assert [s["name"] for s in tight["items"]] == ["Rani ki Vav"]


def test_get_site_detail_includes_entries(client, sites):
    site_id = sites["Rani ki Vav"]["id"]
    client.post(
        f"{API}/entries",
        data={"title": "Morning light", "body": "Carved panels glow at sunrise.", "site_id": site_id},
    )
    detail = client.get(f"{API}/sites/{site_id}").json()
    assert detail["name"] == "Rani ki Vav"
    assert any(e["title"] == "Morning light" for e in detail["entries"])
    assert detail["entry_count"] == len(detail["entries"])


# --- entries ---
def test_entry_auto_attaches_to_nearest_site_within_2km(client, sites):
    res = client.post(
        f"{API}/entries",
        data={
            "title": "Stepwell notes", "body": "A deep stepwell with carved panels.",
            "kind": "journal", "author": "Demo Fellow", "lat": "23.8600", "lng": "72.1020",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["site_id"] == sites["Rani ki Vav"]["id"]
    assert body["auto_attached"] is True
    assert body["author"] == "Demo Fellow"
    assert body["language"] == "en"
    assert set(body["tags"]) >= {"site_type", "era", "century", "themes", "language", "source"}


def test_entry_far_from_any_site_stays_unattached(client, sites):
    res = client.post(
        f"{API}/entries",
        data={"title": "Far away", "body": "Mumbai note.", "lat": "19.0760", "lng": "72.8777"},
    )
    assert res.status_code == 201
    assert res.json()["site_id"] is None
    assert res.json()["auto_attached"] is False


def test_entry_explicit_site_id_wins_over_coordinates(client, sites):
    modhera = sites["Modhera Sun Temple"]["id"]
    res = client.post(
        f"{API}/entries",
        data={"title": "Override", "body": "x", "site_id": modhera,
              "lat": "23.8600", "lng": "72.1020"},
    )
    assert res.json()["site_id"] == modhera
    assert res.json()["auto_attached"] is False


def test_entry_hindi_text_is_detected(client, sites):
    res = client.post(
        f"{API}/entries",
        data={"title": "रानी की वाव", "body": "पाटन की रानी की वाव सोलंकी काल की बावड़ी है।"},
    )
    assert res.status_code == 201
    assert res.json()["language"] == "hi"


def test_entry_unknown_site_is_404(client):
    res = client.post(
        f"{API}/entries",
        data={"title": "t", "body": "b", "site_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"body": "no title"},
        {"title": "t", "kind": "podcast"},
        {"title": "t", "lat": "23.0"},
        {"title": "t", "lat": "abc", "lng": "72"},
        {"title": "t", "lat": "95", "lng": "72"},
        {"title": "t", "site_id": "not-a-uuid"},
    ],
)
def test_entry_validation_errors_are_422_envelopes(client, data):
    res = client.post(f"{API}/entries", data=data)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_entry_with_image_is_stored_and_served(client):
    res = client.post(
        f"{API}/entries",
        data={"title": "Photo", "body": "carving", "kind": "photo"},
        files={"image": ("../../evil name.png", png_bytes(), "image/png")},
    )
    assert res.status_code == 201, res.text
    url = res.json()["image_url"]
    assert url.startswith("/media/") and url.endswith(".png")
    assert "evil" not in url  # random server-side name, client filename unused
    served = client.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"


def test_entry_rejects_non_image_with_image_name(client):
    res = client.post(
        f"{API}/entries",
        data={"title": "Fake", "body": "x"},
        files={"image": ("photo.png", b"this is plain text, not a png", "image/png")},
    )
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_entry_rejects_svg(client):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    res = client.post(
        f"{API}/entries",
        data={"title": "Svg", "body": "x"},
        files={"image": ("a.svg", svg, "image/svg+xml")},
    )
    assert res.status_code == 415


def test_entry_oversized_image_is_413(client):
    # 8.5 MB passes the request-size guard, so this exercises the per-file limit.
    res = client.post(
        f"{API}/entries",
        data={"title": "Big", "body": "x"},
        files={"image": ("big.png", b"\0" * int(8.5 * 1024 * 1024), "image/png")},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_request_far_over_limit_is_rejected_early(client):
    res = client.post(
        f"{API}/entries",
        data={"title": "Huge", "body": "x"},
        files={"image": ("huge.png", b"\0" * (10 * 1024 * 1024), "image/png")},
    )
    assert res.status_code == 413


def test_get_entry_by_id(client):
    created = client.post(f"{API}/entries", data={"title": "Lookup", "body": "b"}).json()
    assert client.get(f"{API}/entries/{created['id']}").json()["title"] == "Lookup"


# --- tag, meta, search, trails ---
def test_tag_endpoint_shape(client):
    res = client.post(f"{API}/tag", json={"text": "An 11th century stepwell in Patan"})
    assert res.status_code == 200
    body = res.json()
    assert body["site_type"] == "stepwell"
    assert body["century"] == 11
    assert body["language"] == "en"


def test_tag_rejects_empty_text(client):
    assert client.post(f"{API}/tag", json={"text": ""}).status_code == 422


def test_meta_counts(client, sites):
    meta = client.get(f"{API}/meta").json()
    types = {t["value"]: t["count"] for t in meta["types"]}
    assert types["stepwell"] >= 1 and types["temple"] >= 1
    assert meta["sites"] >= 2
    assert meta["entries"] >= 1
    assert {"value": "unesco", "count": 1} in meta["themes"]
    assert any(l["value"] == "en" for l in meta["languages"])


def test_search_finds_site_and_entry(client, sites):
    res = client.get(f"{API}/search", params={"q": "stepwell", "k": 5}).json()
    assert res["query"] == "stepwell"
    titles = [r["title"] for r in res["results"]]
    assert "Rani ki Vav" in titles
    top = res["results"][0]
    assert top["score"] > 0 and top["snippet"]


def test_search_finds_hindi_entry(client, sites):
    client.post(
        f"{API}/entries",
        data={"title": "बावड़ी की यात्रा", "body": "सुबह की रोशनी में नक्काशीदार पत्थर चमक उठे।"},
    )
    res = client.get(f"{API}/search", params={"q": "बावड़ी"}).json()
    assert any(r["language"] == "hi" for r in res["results"])


def test_search_requires_query(client):
    assert client.get(f"{API}/search").status_code == 422
    assert client.get(f"{API}/search", params={"q": "x", "k": 500}).status_code == 422


def test_trail_from_site_ids(client, sites):
    ids = [sites["Rani ki Vav"]["id"], sites["Modhera Sun Temple"]["id"]]
    res = client.post(f"{API}/trails", json={"site_ids": ids, "max_stops": 5})
    assert res.status_code == 200, res.text
    trail = res.json()
    assert [s["order"] for s in trail["stops"]] == [1, 2]
    assert {s["id"] for s in trail["stops"]} == set(ids)
    assert 25 < trail["total_km"] < 50  # Patan to Modhera is about 33 km in a straight line
    assert trail["est_hours"] > 2  # 2 stops = 2 h plus travel time
    assert len(trail["polyline"]) >= 2 and len(trail["polyline"][0]) == 2


def test_trail_by_theme_and_start(client, sites):
    res = client.post(
        f"{API}/trails",
        json={"theme": "stone-carving", "start_lat": 23.2156, "start_lng": 72.6369},
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["stops"]) >= 2


def test_trail_errors(client, sites):
    one = [sites["Rani ki Vav"]["id"]]
    assert client.post(f"{API}/trails", json={"site_ids": one}).status_code == 422
    assert client.post(f"{API}/trails", json={"theme": "nonsense"}).status_code == 422
    assert client.post(f"{API}/trails", json={"max_stops": 1}).status_code == 422
    assert client.post(f"{API}/trails", json={"start_lat": 23.0}).status_code == 422
    missing = {"site_ids": [one[0], "00000000-0000-0000-0000-000000000000"]}
    assert client.post(f"{API}/trails", json=missing).status_code == 404


# --- OCR ---
def test_ocr_returns_501_when_tesseract_missing(client, monkeypatch):
    monkeypatch.setattr(ocr_service, "tesseract_available", lambda: False)
    res = client.post(
        f"{API}/ocr", files={"file": ("scan.png", png_bytes(), "image/png")}
    )
    assert res.status_code == 501
    err = res.json()["error"]
    assert err["code"] == "NOT_IMPLEMENTED"
    assert "Tesseract" in err["message"]


def test_ocr_rejects_bad_lang(client, monkeypatch):
    monkeypatch.setattr(ocr_service, "tesseract_available", lambda: True)
    for lang in ("eng --psm 1", "../../x", "hin+", "e"):
        res = client.post(
            f"{API}/ocr",
            data={"lang": lang},
            files={"file": ("scan.png", png_bytes(), "image/png")},
        )
        assert res.status_code == 422, lang


def test_ocr_rejects_non_image(client, monkeypatch):
    monkeypatch.setattr(ocr_service, "tesseract_available", lambda: True)
    res = client.post(f"{API}/ocr", files={"file": ("scan.png", b"not an image", "image/png")})
    assert res.status_code == 415


def test_ocr_success_returns_text_language_and_tags(client, monkeypatch):
    monkeypatch.setattr(ocr_service, "tesseract_available", lambda: True)
    monkeypatch.setattr(
        ocr_service, "run_ocr", lambda data, lang: "रानी की वाव ग्यारहवीं सदी की बावड़ी है"
    )
    res = client.post(
        f"{API}/ocr", files={"file": ("scan.png", png_bytes(), "image/png")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["language"] == "hi"
    assert body["tags"]["language"] == "hi"
    assert "वाव" in body["text"]


def test_ocr_lang_pattern():
    assert ocr_service.valid_lang("hin+eng")
    assert ocr_service.valid_lang("guj")
    assert not ocr_service.valid_lang("hin; rm")
    assert not ocr_service.valid_lang("")


def test_site_image_lookup_uses_backend_and_degrades(client, monkeypatch):
    """GET /sites/{id}/image returns the looked-up photo, or empty fields when none is found."""
    from app.services import site_images

    site_id = client.get("/api/v1/sites").json()["items"][0]["id"]
    found = {"image_url": "https://upload.wikimedia.org/x.jpg", "page_url": "https://en.wikipedia.org/wiki/X",
             "title": "X", "source": "Wikipedia"}

    async def fake_found(name):
        return found

    async def fake_none(name):
        return None

    monkeypatch.setattr(site_images, "get_site_image", fake_found)
    assert client.get(f"/api/v1/sites/{site_id}/image").json()["image_url"] == found["image_url"]

    monkeypatch.setattr(site_images, "get_site_image", fake_none)
    assert client.get(f"/api/v1/sites/{site_id}/image").json() == {
        "image_url": None, "page_url": None, "title": None, "source": None}

    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/sites/{missing}/image").status_code == 404

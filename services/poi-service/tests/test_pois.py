"""Tests: POI create + validate + publish workflow."""

from tests.conftest import HEADERS


def test_create_poi(client):
    resp = client.post(
        "/pois",
        json={
            "name": "Test POI",
            "description": "A test point of interest",
            "address": "123 Test St",
            "lat": 48.8566,
            "lon": 2.3522,
            "poi_type": "restaurant",
            "tags": ["test"],
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test POI"
    assert data["status"] == "draft"
    assert data["version"] == 1


def test_list_pois(client):
    # Create 2 POIs
    for i in range(2):
        client.post(
            "/pois",
            json={"name": f"POI {i}", "lat": 48.0 + i, "lon": 2.0 + i},
            headers=HEADERS,
        )
    resp = client.get("/pois", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_get_poi(client):
    resp = client.post(
        "/pois",
        json={"name": "Findable POI", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]
    resp = client.get(f"/pois/{poi_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Findable POI"


def test_update_poi(client):
    resp = client.post(
        "/pois",
        json={"name": "Original", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]
    resp = client.patch(
        f"/pois/{poi_id}",
        json={"name": "Updated"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


def test_validate_poi(client):
    resp = client.post(
        "/pois",
        json={"name": "To Validate", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]

    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "validated"


def test_publish_poi(client):
    resp = client.post(
        "/pois",
        json={"name": "To Publish", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]

    # Validate first
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)

    # Then publish
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_archive_poi(client):
    resp = client.post(
        "/pois",
        json={"name": "To Archive", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]

    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)

    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_cannot_publish_draft(client):
    resp = client.post(
        "/pois",
        json={"name": "Draft", "lat": 48.0, "lon": 2.0},
        headers=HEADERS,
    )
    poi_id = resp.json()["id"]

    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_auth_required(client):
    resp = client.get("/pois")
    assert resp.status_code == 401

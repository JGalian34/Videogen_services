"""Tests: Asset create + list by poi_id."""

import uuid
from tests.conftest import HEADERS

POI_ID = str(uuid.uuid4())


def test_create_asset(client):
    resp = client.post(
        "/assets",
        json={
            "poi_id": POI_ID,
            "name": "facade.jpg",
            "asset_type": "photo",
            "description": "Facade photo",
            "file_path": "/data/assets/facade.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1024000,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "facade.jpg"
    assert data["poi_id"] == POI_ID
    assert data["asset_type"] == "photo"


def test_list_assets_by_poi(client):
    # Create 2 assets for the same POI
    for name in ["photo1.jpg", "photo2.jpg"]:
        client.post(
            "/assets",
            json={"poi_id": POI_ID, "name": name, "asset_type": "photo"},
            headers=HEADERS,
        )
    # Create 1 asset for a different POI
    other_poi = str(uuid.uuid4())
    client.post(
        "/assets",
        json={"poi_id": other_poi, "name": "other.jpg", "asset_type": "photo"},
        headers=HEADERS,
    )

    resp = client.get(f"/assets?poi_id={POI_ID}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


def test_get_asset(client):
    resp = client.post(
        "/assets",
        json={"poi_id": POI_ID, "name": "find-me.jpg"},
        headers=HEADERS,
    )
    asset_id = resp.json()["id"]
    resp = client.get(f"/assets/{asset_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "find-me.jpg"


def test_update_asset(client):
    resp = client.post(
        "/assets",
        json={"poi_id": POI_ID, "name": "old-name.jpg"},
        headers=HEADERS,
    )
    asset_id = resp.json()["id"]
    resp = client.patch(
        f"/assets/{asset_id}",
        json={"name": "new-name.jpg"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new-name.jpg"
    assert resp.json()["version"] == 2


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200


# ── Error tests ────────────────────────────────────────────────────

def test_get_asset_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/assets/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_update_asset_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.patch(f"/assets/{fake_id}", json={"name": "x"}, headers=HEADERS)
    assert resp.status_code == 404


def test_create_asset_missing_api_key(client):
    resp = client.post("/assets", json={"poi_id": POI_ID, "name": "x"})
    assert resp.status_code == 401


def test_create_asset_invalid_body(client):
    resp = client.post("/assets", json={}, headers=HEADERS)
    assert resp.status_code == 422


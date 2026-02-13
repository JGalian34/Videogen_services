"""
Functional pipeline tests – Asset service.

Tests the complete asset lifecycle with realistic mock data:
  create multiple assets for a POI, update, list with filters and pagination.
"""

import uuid

from tests.conftest import HEADERS


# ── Mock data (realistic Michelin-quality assets) ─────────────────────────

POI_ID = str(uuid.uuid4())

MOCK_ASSETS = [
    {
        "poi_id": POI_ID,
        "name": "facade_principale.jpg",
        "asset_type": "photo",
        "description": "Vue de la façade principale depuis le portail d'entrée",
        "file_path": "/data/assets/villa_paradiso/facade_principale.jpg",
        "mime_type": "image/jpeg",
        "file_size": 4_200_000,
        "metadata": {"resolution": "4032x3024", "camera": "Sony A7R IV", "hdr": True},
    },
    {
        "poi_id": POI_ID,
        "name": "plan_architecte_rdc.pdf",
        "asset_type": "plan",
        "description": "Plan architecte du rez-de-chaussée",
        "file_path": "/data/assets/villa_paradiso/plan_rdc.pdf",
        "mime_type": "application/pdf",
        "file_size": 850_000,
        "metadata": {"scale": "1:100", "floor": "ground"},
    },
    {
        "poi_id": POI_ID,
        "name": "visite_virtuelle_raw.mp4",
        "asset_type": "raw_video",
        "description": "Captation vidéo brute de la visite complète (drone + intérieur)",
        "file_path": "/data/assets/villa_paradiso/visite_raw.mp4",
        "mime_type": "video/mp4",
        "file_size": 1_200_000_000,
        "metadata": {"duration_seconds": 180, "resolution": "4K", "fps": 60},
    },
    {
        "poi_id": POI_ID,
        "name": "piscine_drone.jpg",
        "asset_type": "photo",
        "description": "Vue aérienne drone de la piscine à débordement et du jardin",
        "file_path": "/data/assets/villa_paradiso/piscine_drone.jpg",
        "mime_type": "image/jpeg",
        "file_size": 5_100_000,
        "metadata": {"resolution": "5472x3648", "drone": "DJI Mavic 3 Pro"},
    },
]


def test_full_asset_lifecycle(client):
    """Create multiple assets, verify listing, update, and version bumping."""
    created_ids = []

    # 1) Create all assets
    for asset_data in MOCK_ASSETS:
        resp = client.post("/assets", json=asset_data, headers=HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["poi_id"] == POI_ID
        assert data["version"] == 1
        created_ids.append(data["id"])

    # 2) List all assets for this POI
    resp = client.get(f"/assets?poi_id={POI_ID}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4

    # 3) Get a specific asset
    resp = client.get(f"/assets/{created_ids[0]}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "facade_principale.jpg"
    assert resp.json()["metadata"]["camera"] == "Sony A7R IV"

    # 4) Update asset (should bump version)
    resp = client.patch(
        f"/assets/{created_ids[0]}",
        json={"description": "Façade rénovée – après travaux 2025"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert "rénovée" in resp.json()["description"]


def test_assets_isolation_by_poi(client):
    """Verify assets from different POIs don't leak into each other's lists."""
    poi_a = str(uuid.uuid4())
    poi_b = str(uuid.uuid4())

    # Create 3 assets for POI A
    for i in range(3):
        client.post(
            "/assets",
            json={"poi_id": poi_a, "name": f"a_{i}.jpg", "asset_type": "photo"},
            headers=HEADERS,
        )

    # Create 2 assets for POI B
    for i in range(2):
        client.post(
            "/assets",
            json={"poi_id": poi_b, "name": f"b_{i}.jpg", "asset_type": "photo"},
            headers=HEADERS,
        )

    # List POI A
    resp = client.get(f"/assets?poi_id={poi_a}", headers=HEADERS)
    assert resp.json()["total"] == 3

    # List POI B
    resp = client.get(f"/assets?poi_id={poi_b}", headers=HEADERS)
    assert resp.json()["total"] == 2


def test_asset_pagination(client):
    """Test pagination on asset listing."""
    poi_id = str(uuid.uuid4())
    for i in range(5):
        client.post(
            "/assets",
            json={"poi_id": poi_id, "name": f"p_{i}.jpg", "asset_type": "photo"},
            headers=HEADERS,
        )

    resp = client.get(f"/assets?poi_id={poi_id}&page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp = client.get(f"/assets?poi_id={poi_id}&page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1


def test_readyz_without_real_db(client):
    """In unit-test mode (SQLite), /readyz returns 503 because it checks the real PG engine."""
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)


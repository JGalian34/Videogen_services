"""
Functional pipeline tests – Asset Service (Enterprise-grade).

Tests the complete asset lifecycle with realistic mock data:
  - Multi-POI asset catalog management
  - All asset types in a single property
  - Bulk creation → listing → update → version tracking
  - POI isolation (assets from POI A never leak into POI B)
  - Rich metadata preservation through updates
"""

import uuid

from tests.conftest import HEADERS


# ── Mock data: complete property media catalog ──────────────────────

POI_ID_VILLA = str(uuid.uuid4())
POI_ID_APARTMENT = str(uuid.uuid4())

VILLA_ASSETS = [
    {
        "poi_id": POI_ID_VILLA,
        "name": "facade-aerienne-drone.jpg",
        "asset_type": "photo",
        "description": "Vue aérienne drone DJI Mavic 3, altitude 30m",
        "file_path": "/data/villa/facade-drone.jpg",
        "mime_type": "image/jpeg",
        "file_size": 5_200_000,
        "metadata": {"camera": "DJI Mavic 3", "resolution": "5280x3956"},
    },
    {
        "poi_id": POI_ID_VILLA,
        "name": "salon-panoramique.jpg",
        "asset_type": "photo",
        "description": "Salon avec baies vitrées et vue Alpilles",
        "file_path": "/data/villa/salon.jpg",
        "mime_type": "image/jpeg",
        "file_size": 3_800_000,
    },
    {
        "poi_id": POI_ID_VILLA,
        "name": "piscine-debordement.jpg",
        "asset_type": "photo",
        "description": "Piscine à débordement, coucher de soleil",
        "file_path": "/data/villa/piscine.jpg",
        "mime_type": "image/jpeg",
        "file_size": 4_100_000,
    },
    {
        "poi_id": POI_ID_VILLA,
        "name": "plan-rdc.pdf",
        "asset_type": "floor_plan",
        "description": "Plan RDC échelle 1/100",
        "file_path": "/data/villa/plan-rdc.pdf",
        "mime_type": "application/pdf",
        "file_size": 920_000,
    },
    {
        "poi_id": POI_ID_VILLA,
        "name": "visite-virtuelle.mp4",
        "asset_type": "raw_video",
        "description": "Visite 4K HDR 3min24s",
        "file_path": "/data/villa/visite-4k.mp4",
        "mime_type": "video/mp4",
        "file_size": 450_000_000,
        "metadata": {"duration_seconds": 204, "codec": "h265"},
    },
    {
        "poi_id": POI_ID_VILLA,
        "name": "dpe-classe-a.pdf",
        "asset_type": "document",
        "description": "Diagnostic de Performance Énergétique – Classe A",
        "file_path": "/data/villa/dpe.pdf",
        "mime_type": "application/pdf",
        "file_size": 150_000,
    },
]

APARTMENT_ASSETS = [
    {
        "poi_id": POI_ID_APARTMENT,
        "name": "vue-toits-paris.jpg",
        "asset_type": "photo",
        "description": "Vue panoramique toits de Paris depuis balcon 3ème étage",
        "file_path": "/data/apartment/vue-toits.jpg",
        "mime_type": "image/jpeg",
        "file_size": 2_900_000,
    },
    {
        "poi_id": POI_ID_APARTMENT,
        "name": "parquet-hongrie.jpg",
        "asset_type": "photo",
        "description": "Détail parquet point de Hongrie d'origine",
        "file_path": "/data/apartment/parquet.jpg",
        "mime_type": "image/jpeg",
        "file_size": 1_800_000,
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline: Complete property media catalog
# ═══════════════════════════════════════════════════════════════════════


def test_full_asset_lifecycle(client):
    """Create → list → get → update → verify version tracking."""
    # 1) Create all villa assets
    asset_ids = []
    for mock in VILLA_ASSETS:
        resp = client.post("/assets", json=mock, headers=HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1
        assert data["poi_id"] == POI_ID_VILLA
        asset_ids.append(data["id"])

    assert len(asset_ids) == 6

    # 2) List all villa assets
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 6

    # 3) Verify each asset type is present
    types_found = {a["asset_type"] for a in data["items"]}
    assert types_found == {"photo", "floor_plan", "raw_video", "document"}

    # 4) Get specific asset and verify full details
    resp = client.get(f"/assets/{asset_ids[0]}", headers=HEADERS)
    assert resp.status_code == 200
    facade = resp.json()
    assert facade["name"] == "facade-aerienne-drone.jpg"
    assert facade["metadata"]["camera"] == "DJI Mavic 3"

    # 5) Update asset → version bump
    resp = client.patch(
        f"/assets/{asset_ids[0]}",
        json={"description": "Vue aérienne retouchée, contraste amélioré"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert "retouchée" in resp.json()["description"]

    # 6) Verify metadata preserved after description update
    resp = client.get(f"/assets/{asset_ids[0]}", headers=HEADERS)
    assert resp.json()["metadata"]["camera"] == "DJI Mavic 3"  # Not overwritten


def test_multi_poi_asset_isolation(client):
    """Assets from different POIs must be completely isolated."""
    # Create villa + apartment assets
    for mock in VILLA_ASSETS[:3]:
        client.post("/assets", json=mock, headers=HEADERS)
    for mock in APARTMENT_ASSETS:
        client.post("/assets", json=mock, headers=HEADERS)

    # Villa: 3 assets
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}", headers=HEADERS)
    assert resp.json()["total"] == 3
    assert all(a["poi_id"] == POI_ID_VILLA for a in resp.json()["items"])

    # Apartment: 2 assets
    resp = client.get(f"/assets?poi_id={POI_ID_APARTMENT}", headers=HEADERS)
    assert resp.json()["total"] == 2
    assert all(a["poi_id"] == POI_ID_APARTMENT for a in resp.json()["items"])

    # All: 5 assets total
    resp = client.get("/assets", headers=HEADERS)
    assert resp.json()["total"] == 5


def test_asset_pagination_pipeline(client):
    """Create 8 assets, paginate through them."""
    for i in range(8):
        client.post(
            "/assets",
            json={"poi_id": POI_ID_VILLA, "name": f"photo-{i:03d}.jpg", "asset_type": "photo"},
            headers=HEADERS,
        )

    # Page 1: 3 items
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=1&page_size=3", headers=HEADERS)
    page1 = resp.json()
    assert page1["total"] == 8
    assert len(page1["items"]) == 3

    # Page 2: 3 items
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=2&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 3

    # Page 3: 2 items
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=3&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 2

    # Page 4: 0 items
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=4&page_size=3", headers=HEADERS)
    assert resp.json()["items"] == []


def test_sequential_updates_track_version(client):
    """Multiple updates to the same asset should increment version correctly."""
    resp = client.post("/assets", json=MOCK_VILLA_ASSETS_MINIMAL, headers=HEADERS)
    asset_id = resp.json()["id"]
    assert resp.json()["version"] == 1

    for i in range(5):
        resp = client.patch(
            f"/assets/{asset_id}",
            json={"name": f"iteration-{i + 1}.jpg"},
            headers=HEADERS,
        )
        assert resp.json()["version"] == i + 2


def test_video_asset_rich_metadata(client):
    """Verify large file sizes and nested metadata preserved."""
    MOCK_RAW_VIDEO = {
        "poi_id": POI_ID_VILLA,
        "name": "visite-4k-raw.mp4",
        "asset_type": "raw_video",
        "description": "Rush vidéo 4K HDR drone + intérieur",
        "file_path": "/data/villa/visite-4k.mp4",
        "mime_type": "video/mp4",
        "file_size": 450_000_000,
        "metadata": {"duration_seconds": 204, "codec": "h265", "resolution": "3840x2160"},
    }
    resp = client.post("/assets", json=MOCK_RAW_VIDEO, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_size"] == 450_000_000
    assert data["metadata"]["duration_seconds"] == 204
    assert data["metadata"]["codec"] == "h265"


# Minimal mock for sequential update test
MOCK_VILLA_ASSETS_MINIMAL = {
    "poi_id": POI_ID_VILLA,
    "name": "iteration-0.jpg",
    "asset_type": "photo",
}

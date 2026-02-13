"""
Enterprise-grade unit tests – Asset Service.

Coverage:
  - CRUD: create, read, update, list
  - All asset types: photo, floor_plan, raw_video, document, other
  - Schema response validation: all fields present, correct types
  - Pagination: page/page_size, filter by poi_id, empty results
  - File metadata: mime_type, file_size, file_path persistence
  - Version bumping on updates
  - Auth: missing key → 401, health bypasses auth
  - Error paths: 404, 422 with structured body
  - Data integrity: metadata preservation, multi-POI isolation

Mock data: realistic French luxury property asset catalog.
"""

import uuid

from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Mock data – realistic property media assets
# ═══════════════════════════════════════════════════════════════════════

POI_ID_VILLA = str(uuid.uuid4())
POI_ID_APARTMENT = str(uuid.uuid4())
POI_ID_OTHER = str(uuid.uuid4())

MOCK_PHOTO_FACADE = {
    "poi_id": POI_ID_VILLA,
    "name": "facade-principale-villa-paradiso.jpg",
    "asset_type": "photo",
    "description": "Photo de la façade principale, prise au drone DJI Mavic 3",
    "file_path": "/data/assets/villa-paradiso/facade-principale.jpg",
    "mime_type": "image/jpeg",
    "file_size": 4_500_000,
    "metadata": {
        "camera": "DJI Mavic 3",
        "resolution": "5280x3956",
        "gps_lat": 43.7439,
        "gps_lon": 4.7953,
    },
}

MOCK_PHOTO_INTERIOR = {
    "poi_id": POI_ID_VILLA,
    "name": "salon-lumineux.jpg",
    "asset_type": "photo",
    "description": "Vue panoramique du salon avec baies vitrées",
    "file_path": "/data/assets/villa-paradiso/salon.jpg",
    "mime_type": "image/jpeg",
    "file_size": 3_200_000,
}

MOCK_FLOOR_PLAN = {
    "poi_id": POI_ID_VILLA,
    "name": "plan-rdc-villa.pdf",
    "asset_type": "floor_plan",
    "description": "Plan du rez-de-chaussée, échelle 1/100",
    "file_path": "/data/assets/villa-paradiso/plan-rdc.pdf",
    "mime_type": "application/pdf",
    "file_size": 850_000,
}

MOCK_RAW_VIDEO = {
    "poi_id": POI_ID_VILLA,
    "name": "visite-virtuelle-4k.mp4",
    "asset_type": "raw_video",
    "description": "Visite virtuelle complète 4K HDR, 3 min 24s",
    "file_path": "/data/assets/villa-paradiso/visite-4k.mp4",
    "mime_type": "video/mp4",
    "file_size": 450_000_000,
    "metadata": {"duration_seconds": 204, "codec": "h265", "resolution": "3840x2160"},
}

MOCK_DOCUMENT = {
    "poi_id": POI_ID_VILLA,
    "name": "diagnostic-energetique-dpe.pdf",
    "asset_type": "document",
    "description": "Diagnostic de Performance Énergétique – Classe A",
    "file_path": "/data/assets/villa-paradiso/dpe.pdf",
    "mime_type": "application/pdf",
    "file_size": 120_000,
}

MOCK_APARTMENT_PHOTO = {
    "poi_id": POI_ID_APARTMENT,
    "name": "vue-toits-paris.jpg",
    "asset_type": "photo",
    "description": "Vue depuis le balcon sur les toits de Paris",
    "file_path": "/data/assets/apartment-haussmann/vue-toits.jpg",
    "mime_type": "image/jpeg",
    "file_size": 2_800_000,
}

MOCK_MINIMAL = {
    "poi_id": POI_ID_VILLA,
    "name": "minimal-asset.jpg",
}


# ═══════════════════════════════════════════════════════════════════════
#  Schema helpers
# ═══════════════════════════════════════════════════════════════════════

ASSET_RESPONSE_FIELDS = [
    "id", "poi_id", "name", "asset_type", "description",
    "file_path", "mime_type", "file_size", "metadata",
    "version", "created_at", "updated_at",
]


def _assert_asset_schema(data: dict) -> None:
    """Assert all required fields present in Asset response."""
    for field in ASSET_RESPONSE_FIELDS:
        assert field in data, f"Missing field '{field}' in Asset response"
    assert isinstance(data["id"], str) and len(data["id"]) == 36
    assert isinstance(data["version"], int)
    assert isinstance(data["metadata"], dict)


# ═══════════════════════════════════════════════════════════════════════
#  CREATE – Happy paths
# ═══════════════════════════════════════════════════════════════════════


def test_create_asset_photo_full_payload(client):
    """Create photo asset with all fields – verify full response schema."""
    resp = client.post("/assets", json=MOCK_PHOTO_FACADE, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    _assert_asset_schema(data)
    assert data["name"] == "facade-principale-villa-paradiso.jpg"
    assert data["poi_id"] == POI_ID_VILLA
    assert data["asset_type"] == "photo"
    assert data["description"] == MOCK_PHOTO_FACADE["description"]
    assert data["file_path"] == MOCK_PHOTO_FACADE["file_path"]
    assert data["mime_type"] == "image/jpeg"
    assert data["file_size"] == 4_500_000
    assert data["metadata"]["camera"] == "DJI Mavic 3"
    assert data["version"] == 1


def test_create_asset_floor_plan(client):
    resp = client.post("/assets", json=MOCK_FLOOR_PLAN, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["asset_type"] == "floor_plan"
    assert data["mime_type"] == "application/pdf"


def test_create_asset_raw_video(client):
    resp = client.post("/assets", json=MOCK_RAW_VIDEO, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["asset_type"] == "raw_video"
    assert data["file_size"] == 450_000_000
    assert data["metadata"]["codec"] == "h265"


def test_create_asset_document(client):
    resp = client.post("/assets", json=MOCK_DOCUMENT, headers=HEADERS)
    assert resp.status_code == 201
    assert resp.json()["asset_type"] == "document"


def test_create_asset_minimal_payload(client):
    """Create with minimum required fields – defaults applied."""
    resp = client.post("/assets", json=MOCK_MINIMAL, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    _assert_asset_schema(data)
    assert data["asset_type"] == "photo"  # default
    assert data["description"] is None
    assert data["file_path"] is None
    assert data["mime_type"] is None
    assert data["file_size"] is None
    assert data["metadata"] == {}
    assert data["version"] == 1


def test_create_asset_generates_unique_ids(client):
    """Each asset gets a unique UUID."""
    ids = set()
    for i in range(3):
        resp = client.post(
            "/assets",
            json={"poi_id": POI_ID_VILLA, "name": f"asset-{i}.jpg"},
            headers=HEADERS,
        )
        assert resp.status_code == 201
        ids.add(resp.json()["id"])
    assert len(ids) == 3


# ═══════════════════════════════════════════════════════════════════════
#  CREATE – Validation (422)
# ═══════════════════════════════════════════════════════════════════════


def test_create_asset_empty_body(client):
    resp = client.post("/assets", json={}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_asset_missing_poi_id(client):
    resp = client.post("/assets", json={"name": "test.jpg"}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_asset_missing_name(client):
    resp = client.post("/assets", json={"poi_id": POI_ID_VILLA}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_asset_empty_name(client):
    resp = client.post("/assets", json={"poi_id": POI_ID_VILLA, "name": ""}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_asset_name_max_length(client):
    """Name with 500 chars accepted; 501 rejected."""
    resp = client.post(
        "/assets",
        json={"poi_id": POI_ID_VILLA, "name": "A" * 500},
        headers=HEADERS,
    )
    assert resp.status_code == 201

    resp = client.post(
        "/assets",
        json={"poi_id": POI_ID_VILLA, "name": "A" * 501},
        headers=HEADERS,
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  READ – get / list
# ═══════════════════════════════════════════════════════════════════════


def test_get_asset_by_id(client):
    resp = client.post("/assets", json=MOCK_PHOTO_FACADE, headers=HEADERS)
    asset_id = resp.json()["id"]
    resp = client.get(f"/assets/{asset_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    _assert_asset_schema(data)
    assert data["id"] == asset_id


def test_get_asset_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/assets/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body


def test_get_asset_invalid_uuid(client):
    resp = client.get("/assets/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422


def test_list_assets_empty(client):
    resp = client.get("/assets", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_assets_all(client):
    """List all assets without filter."""
    for mock in [MOCK_PHOTO_FACADE, MOCK_FLOOR_PLAN, MOCK_RAW_VIDEO]:
        client.post("/assets", json=mock, headers=HEADERS)
    resp = client.get("/assets", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_list_assets_filter_by_poi_id(client):
    """Assets for POI A should not include POI B assets."""
    client.post("/assets", json=MOCK_PHOTO_FACADE, headers=HEADERS)
    client.post("/assets", json=MOCK_PHOTO_INTERIOR, headers=HEADERS)
    client.post("/assets", json=MOCK_APARTMENT_PHOTO, headers=HEADERS)

    # Villa assets only
    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 2
    assert all(a["poi_id"] == POI_ID_VILLA for a in data["items"])

    # Apartment assets only
    resp = client.get(f"/assets?poi_id={POI_ID_APARTMENT}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["poi_id"] == POI_ID_APARTMENT


def test_list_assets_filter_by_nonexistent_poi(client):
    """Filtering by unknown poi_id returns 0 items (not 404)."""
    client.post("/assets", json=MOCK_PHOTO_FACADE, headers=HEADERS)
    resp = client.get(f"/assets?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ═══════════════════════════════════════════════════════════════════════
#  PAGINATION
# ═══════════════════════════════════════════════════════════════════════


def test_pagination_assets(client):
    """Test pagination on asset listing."""
    for i in range(5):
        client.post(
            "/assets",
            json={"poi_id": POI_ID_VILLA, "name": f"asset-{i:03d}.jpg"},
            headers=HEADERS,
        )

    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1

    resp = client.get(f"/assets?poi_id={POI_ID_VILLA}&page=10&page_size=2", headers=HEADERS)
    assert resp.json()["items"] == []


def test_pagination_page_size_max(client):
    """page_size > 200 should be rejected (le=200 in Query)."""
    resp = client.get("/assets?page_size=201", headers=HEADERS)
    assert resp.status_code == 422


def test_pagination_page_zero_rejected(client):
    resp = client.get("/assets?page=0", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  UPDATE (PATCH)
# ═══════════════════════════════════════════════════════════════════════


def test_update_asset_name(client):
    resp = client.post("/assets", json=MOCK_PHOTO_FACADE, headers=HEADERS)
    asset_id = resp.json()["id"]
    resp = client.patch(
        f"/assets/{asset_id}",
        json={"name": "facade-renovee-2024.jpg"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "facade-renovee-2024.jpg"
    assert data["version"] == 2


def test_update_asset_description(client):
    resp = client.post("/assets", json=MOCK_MINIMAL, headers=HEADERS)
    asset_id = resp.json()["id"]
    resp = client.patch(
        f"/assets/{asset_id}",
        json={"description": "Photo mise à jour avec nouveau cadrage"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Photo mise à jour avec nouveau cadrage"


def test_update_asset_file_metadata(client):
    resp = client.post("/assets", json=MOCK_MINIMAL, headers=HEADERS)
    asset_id = resp.json()["id"]
    resp = client.patch(
        f"/assets/{asset_id}",
        json={
            "file_path": "/data/updated/file.jpg",
            "mime_type": "image/png",
            "file_size": 9_999_999,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_path"] == "/data/updated/file.jpg"
    assert data["mime_type"] == "image/png"
    assert data["file_size"] == 9_999_999


def test_update_asset_metadata(client):
    resp = client.post("/assets", json=MOCK_MINIMAL, headers=HEADERS)
    asset_id = resp.json()["id"]
    resp = client.patch(
        f"/assets/{asset_id}",
        json={"metadata": {"processed": True, "watermarked": False}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["processed"] is True


def test_update_asset_bumps_version(client):
    """Each update should bump version by 1."""
    resp = client.post("/assets", json=MOCK_MINIMAL, headers=HEADERS)
    asset_id = resp.json()["id"]
    assert resp.json()["version"] == 1

    resp = client.patch(f"/assets/{asset_id}", json={"name": "v2"}, headers=HEADERS)
    assert resp.json()["version"] == 2

    resp = client.patch(f"/assets/{asset_id}", json={"name": "v3"}, headers=HEADERS)
    assert resp.json()["version"] == 3


def test_update_asset_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.patch(f"/assets/{fake_id}", json={"name": "x"}, headers=HEADERS)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════════════


def test_auth_required_list(client):
    resp = client.get("/assets")
    assert resp.status_code == 401


def test_auth_required_create(client):
    resp = client.post("/assets", json=MOCK_MINIMAL)
    assert resp.status_code == 401


def test_auth_wrong_key(client):
    resp = client.get("/assets", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
#  HEALTH / READINESS
# ═══════════════════════════════════════════════════════════════════════


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_readyz(client):
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)

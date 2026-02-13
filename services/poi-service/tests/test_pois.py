"""
Enterprise-grade unit tests – POI Service.

Coverage:
  - CRUD: create, read, update, list
  - Workflow state machine: draft → validated → published → archived
  - Pydantic validation: boundary coordinates, max-length, required fields
  - Schema response assertions: all fields present with correct types
  - Pagination: page/page_size boundaries, empty pages
  - Auth: missing key, wrong key, health bypasses auth
  - Error paths: 404, 409, 422 with body validation
  - Business rules: version bumping, status transitions, search/filter

Mock data: realistic French luxury real estate (Michelin-grade).
"""

import uuid

from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Mock data – realistic French real estate
# ═══════════════════════════════════════════════════════════════════════

MOCK_VILLA = {
    "name": "Villa Paradiso – Les Baux-de-Provence",
    "description": (
        "Propriété d'exception de 450m² sur un terrain arboré de 2 hectares. "
        "5 chambres, piscine à débordement, vue panoramique sur les Alpilles."
    ),
    "address": "Route de Maussane, 13520 Les Baux-de-Provence",
    "lat": 43.7439,
    "lon": 4.7953,
    "poi_type": "villa",
    "tags": ["luxury", "pool", "provence", "panoramic_view"],
    "metadata": {
        "surface_m2": 450,
        "land_m2": 20000,
        "bedrooms": 5,
        "price_eur": 2850000,
        "energy_class": "A",
    },
}

MOCK_APARTMENT = {
    "name": "Appartement Haussmannien – Paris 8ème",
    "description": (
        "Magnifique 180m² au 3ème étage, parquet point de Hongrie, "
        "moulures, cheminées en marbre. Vue sur les toits de Paris."
    ),
    "address": "42 Avenue Montaigne, 75008 Paris",
    "lat": 48.8672,
    "lon": 2.3042,
    "poi_type": "apartment",
    "tags": ["haussmann", "luxury", "paris"],
    "metadata": {"surface_m2": 180, "bedrooms": 3, "price_eur": 3200000},
}

MOCK_OFFICE = {
    "name": "Bureau Premium – La Défense",
    "description": "Plateau de 800m² en open space dans la tour Hekla, étage 35.",
    "address": "1 Place du Dôme, 92800 Puteaux",
    "lat": 48.8920,
    "lon": 2.2369,
    "poi_type": "office",
    "tags": ["corporate", "la_defense", "high_floor"],
    "metadata": {"surface_m2": 800, "floor": 35, "price_eur": 15000},
}

MOCK_MINIMAL = {
    "name": "POI Minimal",
    "lat": 48.0,
    "lon": 2.0,
}


# ═══════════════════════════════════════════════════════════════════════
#  Response schema helpers
# ═══════════════════════════════════════════════════════════════════════

POI_RESPONSE_FIELDS = [
    "id", "name", "description", "address", "lat", "lon",
    "poi_type", "tags", "metadata", "status", "version",
    "created_at", "updated_at",
]


def _assert_poi_schema(data: dict) -> None:
    """Assert all required fields present in POI response."""
    for field in POI_RESPONSE_FIELDS:
        assert field in data, f"Missing field '{field}' in POI response"
    # Type checks
    assert isinstance(data["id"], str) and len(data["id"]) == 36, "id must be UUID string"
    assert isinstance(data["tags"], list), "tags must be a list"
    assert isinstance(data["metadata"], dict), "metadata must be a dict"
    assert isinstance(data["version"], int), "version must be int"
    assert data["status"] in ("draft", "validated", "published", "archived"), "invalid status"


# ═══════════════════════════════════════════════════════════════════════
#  CREATE – Happy path + variations
# ═══════════════════════════════════════════════════════════════════════


def test_create_poi_full_payload(client):
    """Create POI with all fields – verify complete response schema."""
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    _assert_poi_schema(data)
    assert data["name"] == MOCK_VILLA["name"]
    assert data["description"] == MOCK_VILLA["description"]
    assert data["address"] == MOCK_VILLA["address"]
    assert abs(data["lat"] - MOCK_VILLA["lat"]) < 0.0001
    assert abs(data["lon"] - MOCK_VILLA["lon"]) < 0.0001
    assert data["poi_type"] == "villa"
    assert data["tags"] == ["luxury", "pool", "provence", "panoramic_view"]
    assert data["metadata"]["surface_m2"] == 450
    assert data["metadata"]["bedrooms"] == 5
    assert data["metadata"]["price_eur"] == 2850000
    assert data["status"] == "draft"
    assert data["version"] == 1


def test_create_poi_minimal_payload(client):
    """Create POI with only required fields – optional fields have defaults."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    _assert_poi_schema(data)
    assert data["description"] is None
    assert data["address"] is None
    assert data["poi_type"] is None
    assert data["tags"] == []
    assert data["metadata"] == {}


def test_create_poi_apartment_type(client):
    """Create apartment POI – verify different poi_type is stored."""
    resp = client.post("/pois", json=MOCK_APARTMENT, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["poi_type"] == "apartment"
    assert data["tags"] == ["haussmann", "luxury", "paris"]


def test_create_poi_office_type(client):
    """Create office POI – verify business metadata preserved."""
    resp = client.post("/pois", json=MOCK_OFFICE, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["poi_type"] == "office"
    assert data["metadata"]["floor"] == 35


def test_create_poi_generates_uuid(client):
    """Each created POI gets a unique UUID."""
    ids = set()
    for _ in range(3):
        resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
        assert resp.status_code == 201
        ids.add(resp.json()["id"])
    assert len(ids) == 3, "All POI IDs must be unique"


def test_create_poi_timestamps(client):
    """created_at and updated_at are set and valid ISO format."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    data = resp.json()
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert "T" in data["created_at"], "created_at must be ISO format"


# ═══════════════════════════════════════════════════════════════════════
#  CREATE – Validation (422)
# ═══════════════════════════════════════════════════════════════════════


def test_create_poi_invalid_lat_above_90(client):
    resp = client.post("/pois", json={"name": "Bad", "lat": 91.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_invalid_lat_below_minus_90(client):
    resp = client.post("/pois", json={"name": "Bad", "lat": -91.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_invalid_lon_above_180(client):
    resp = client.post("/pois", json={"name": "Bad", "lat": 48.0, "lon": 181.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_invalid_lon_below_minus_180(client):
    resp = client.post("/pois", json={"name": "Bad", "lat": 48.0, "lon": -181.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_boundary_coordinates_valid(client):
    """Exact boundary values: lat=±90, lon=±180 must be accepted."""
    for lat, lon in [(90.0, 180.0), (-90.0, -180.0), (0.0, 0.0)]:
        resp = client.post("/pois", json={"name": f"Boundary {lat},{lon}", "lat": lat, "lon": lon}, headers=HEADERS)
        assert resp.status_code == 201, f"lat={lat}, lon={lon} should be valid"


def test_create_poi_missing_name(client):
    resp = client.post("/pois", json={"lat": 48.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_empty_name(client):
    resp = client.post("/pois", json={"name": "", "lat": 48.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_missing_lat(client):
    resp = client.post("/pois", json={"name": "No Lat", "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_missing_lon(client):
    resp = client.post("/pois", json={"name": "No Lon", "lat": 48.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_empty_body(client):
    resp = client.post("/pois", json={}, headers=HEADERS)
    assert resp.status_code == 422


def test_create_poi_name_max_length(client):
    """Name with exactly 500 chars should be accepted; 501 rejected."""
    name_500 = "A" * 500
    resp = client.post("/pois", json={"name": name_500, "lat": 48.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 201

    name_501 = "A" * 501
    resp = client.post("/pois", json={"name": name_501, "lat": 48.0, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  READ – get / list
# ═══════════════════════════════════════════════════════════════════════


def test_get_poi_by_id(client):
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.get(f"/pois/{poi_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    _assert_poi_schema(data)
    assert data["id"] == poi_id
    assert data["name"] == MOCK_VILLA["name"]


def test_get_poi_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/pois/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body


def test_get_poi_invalid_uuid_format(client):
    """Invalid UUID format should return 422."""
    resp = client.get("/pois/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422


def test_list_pois_empty(client):
    resp = client.get("/pois", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_pois_multiple(client):
    for mock in [MOCK_VILLA, MOCK_APARTMENT, MOCK_OFFICE]:
        client.post("/pois", json=mock, headers=HEADERS)
    resp = client.get("/pois", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    for item in data["items"]:
        _assert_poi_schema(item)


def test_list_pois_filter_by_status(client):
    resp1 = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    resp2 = client.post("/pois", json=MOCK_APARTMENT, headers=HEADERS)
    poi_id = resp1.json()["id"]
    # Validate one POI
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)

    # Filter draft only
    resp = client.get("/pois?status=draft", headers=HEADERS)
    assert resp.status_code == 200
    assert all(p["status"] == "draft" for p in resp.json()["items"])

    # Filter validated only
    resp = client.get("/pois?status=validated", headers=HEADERS)
    assert resp.status_code == 200
    assert all(p["status"] == "validated" for p in resp.json()["items"])


def test_list_pois_filter_by_poi_type(client):
    client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    client.post("/pois", json=MOCK_APARTMENT, headers=HEADERS)
    client.post("/pois", json=MOCK_OFFICE, headers=HEADERS)

    resp = client.get("/pois?poi_type=villa", headers=HEADERS)
    data = resp.json()
    assert data["total"] >= 1
    assert all(p["poi_type"] == "villa" for p in data["items"])


def test_list_pois_search_by_query(client):
    client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    client.post("/pois", json=MOCK_APARTMENT, headers=HEADERS)

    resp = client.get("/pois?query=Provence", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_list_pois_search_by_address(client):
    client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    resp = client.get("/pois?query=Maussane", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ═══════════════════════════════════════════════════════════════════════
#  PAGINATION
# ═══════════════════════════════════════════════════════════════════════


def test_pagination_page_and_page_size(client):
    for i in range(5):
        client.post("/pois", json={"name": f"POI-{i}", "lat": 48.0 + i * 0.01, "lon": 2.0}, headers=HEADERS)

    resp = client.get("/pois?page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_pagination_last_page(client):
    for i in range(5):
        client.post("/pois", json={"name": f"POI-{i}", "lat": 48.0, "lon": 2.0}, headers=HEADERS)

    resp = client.get("/pois?page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1


def test_pagination_beyond_last_page(client):
    for i in range(3):
        client.post("/pois", json={"name": f"POI-{i}", "lat": 48.0, "lon": 2.0}, headers=HEADERS)

    resp = client.get("/pois?page=100&page_size=10", headers=HEADERS)
    assert resp.json()["items"] == []


def test_pagination_page_size_max_100(client):
    """page_size > 100 should be rejected (le=100 in Query)."""
    resp = client.get("/pois?page_size=101", headers=HEADERS)
    assert resp.status_code == 422


def test_pagination_page_zero_rejected(client):
    """page=0 should be rejected (ge=1 in Query)."""
    resp = client.get("/pois?page=0", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  UPDATE (PATCH)
# ═══════════════════════════════════════════════════════════════════════


def test_update_poi_name(client):
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"name": "Villa Renommée"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Villa Renommée"


def test_update_poi_description(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"description": "New description"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["description"] == "New description"


def test_update_poi_coordinates(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"lat": 45.0, "lon": 3.0}, headers=HEADERS)
    assert resp.status_code == 200
    assert abs(resp.json()["lat"] - 45.0) < 0.0001
    assert abs(resp.json()["lon"] - 3.0) < 0.0001


def test_update_poi_tags(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"tags": ["new", "tags"]}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["new", "tags"]


def test_update_poi_metadata(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"metadata": {"renovated": True}}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["metadata"]["renovated"] is True


def test_update_poi_multiple_fields(client):
    """Update several fields at once."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(
        f"/pois/{poi_id}",
        json={"name": "Renamed", "description": "Updated", "poi_type": "chalet", "tags": ["ski"]},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed"
    assert data["description"] == "Updated"
    assert data["poi_type"] == "chalet"
    assert data["tags"] == ["ski"]


def test_update_draft_poi_does_not_bump_version(client):
    """Updating a draft POI should NOT bump version (stays 1)."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.patch(f"/pois/{poi_id}", json={"name": "Still Draft"}, headers=HEADERS)
    assert resp.json()["version"] == 1


def test_update_published_poi_bumps_version(client):
    """Updating a published POI MUST bump version."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)

    resp = client.patch(f"/pois/{poi_id}", json={"description": "Post-publish edit"}, headers=HEADERS)
    assert resp.json()["version"] == 2

    resp = client.patch(f"/pois/{poi_id}", json={"description": "Second edit"}, headers=HEADERS)
    assert resp.json()["version"] == 3


def test_update_nonexistent_poi_returns_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.patch(f"/pois/{fake_id}", json={"name": "x"}, headers=HEADERS)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  WORKFLOW: validate → publish → archive
# ═══════════════════════════════════════════════════════════════════════


def test_validate_draft_poi(client):
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "validated"
    _assert_poi_schema(data)


def test_publish_validated_poi(client):
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


def test_archive_published_poi(client):
    resp = client.post("/pois", json=MOCK_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_cannot_publish_draft(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409
    assert "Cannot transition" in resp.json()["detail"]


def test_cannot_archive_draft(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_archive_validated(client):
    """validated → archived is not allowed (must publish first)."""
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_revalidate_validated(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_republish_published(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_rearchive_archived(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_validate_archived(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 409


def test_cannot_publish_archived(client):
    resp = client.post("/pois", json=MOCK_MINIMAL, headers=HEADERS)
    poi_id = resp.json()["id"]
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409


def test_validate_nonexistent_poi(client):
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/pois/{fake_id}/validate", headers=HEADERS)
    assert resp.status_code == 404


def test_publish_nonexistent_poi(client):
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/pois/{fake_id}/publish", headers=HEADERS)
    assert resp.status_code == 404


def test_archive_nonexistent_poi(client):
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/pois/{fake_id}/archive", headers=HEADERS)
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════════════


def test_auth_required_no_key(client):
    resp = client.get("/pois")
    assert resp.status_code == 401


def test_auth_required_wrong_key(client):
    resp = client.get("/pois", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_auth_create_requires_key(client):
    resp = client.post("/pois", json=MOCK_MINIMAL)
    assert resp.status_code == 401


def test_health_bypasses_auth(client):
    """Health endpoints should NOT require API key."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
#  HEALTH / READINESS
# ═══════════════════════════════════════════════════════════════════════


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_readyz(client):
    """In unit-test mode (SQLite), /readyz may return 200 or 503."""
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)

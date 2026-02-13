"""
Functional pipeline tests – POI service.

Tests the complete POI lifecycle with realistic mock data:
  draft → validated → published → archived, with updates and search.
"""

import uuid

from tests.conftest import HEADERS


# ── Mock data (realistic Michelin-quality POI) ────────────────────────────


MOCK_POI_VILLA = {
    "name": "Villa Paradiso – Les Baux-de-Provence",
    "description": (
        "Propriété d'exception de 450m² sur un terrain arboré de 2 hectares. "
        "5 chambres, piscine à débordement, vue imprenable sur les Alpilles. "
        "Prestations haut de gamme : domotique, cave à vin, garage 3 places."
    ),
    "address": "Route de Maussane, 13520 Les Baux-de-Provence",
    "lat": 43.7439,
    "lon": 4.7953,
    "poi_type": "villa",
    "tags": ["luxury", "pool", "provence", "panoramic_view"],
    "metadata": {
        "surface_m2": 450,
        "land_m2": 20000,
        "rooms": 8,
        "bedrooms": 5,
        "price_eur": 2850000,
        "year_built": 2018,
        "energy_class": "A",
    },
}

MOCK_POI_APARTMENT = {
    "name": "Appartement Haussmannien – Paris 8ème",
    "description": (
        "Magnifique appartement de 180m² au 3ème étage d'un immeuble haussmannien. "
        "Parquet point de Hongrie, moulures, cheminées en marbre."
    ),
    "address": "42 Avenue Montaigne, 75008 Paris",
    "lat": 48.8672,
    "lon": 2.3042,
    "poi_type": "apartment",
    "tags": ["haussmann", "luxury", "paris", "balcony"],
    "metadata": {
        "surface_m2": 180,
        "floor": 3,
        "rooms": 6,
        "bedrooms": 3,
        "price_eur": 3200000,
    },
}


# ── Pipeline: Full lifecycle ──────────────────────────────────────────────


def test_full_poi_lifecycle(client):
    """Test complete lifecycle: create → validate → publish → archive."""
    # 1) Create
    resp = client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    assert resp.status_code == 201
    poi = resp.json()
    poi_id = poi["id"]
    assert poi["status"] == "draft"
    assert poi["version"] == 1
    assert poi["name"] == MOCK_POI_VILLA["name"]
    assert poi["metadata"]["surface_m2"] == 450
    assert poi["tags"] == ["luxury", "pool", "provence", "panoramic_view"]

    # 2) Validate
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "validated"

    # 3) Publish
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    # 4) Update published POI (version should bump)
    resp = client.patch(
        f"/pois/{poi_id}",
        json={"description": "Updated description with new renovation details."},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2

    # 5) Archive
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_workflow_error_transitions(client):
    """Test all invalid workflow transitions return 409."""
    # Create a draft POI
    resp = client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)
    poi_id = resp.json()["id"]

    # Cannot publish a draft directly
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409
    assert "Cannot transition" in resp.json()["detail"]

    # Cannot archive a draft
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409

    # Validate first
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 200

    # Cannot validate again (validated → validated not allowed)
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 409

    # Cannot archive validated (must publish first)
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409


def test_search_and_filter(client):
    """Test list with search, status filter, and poi_type filter."""
    # Create 3 POIs
    client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    resp2 = client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)
    apt_id = resp2.json()["id"]

    # Validate the apartment
    client.post(f"/pois/{apt_id}/validate", headers=HEADERS)

    # Filter by status=draft
    resp = client.get("/pois?status=draft", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["status"] == "draft" for p in data["items"])

    # Filter by poi_type=villa
    resp = client.get("/pois?poi_type=villa", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["poi_type"] == "villa" for p in data["items"])

    # Search by text
    resp = client.get("/pois?query=Provence", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_pagination(client):
    """Test pagination with page and page_size params."""
    # Create 5 POIs
    for i in range(5):
        client.post(
            "/pois",
            json={"name": f"POI-{i}", "lat": 48.0 + i * 0.01, "lon": 2.0 + i * 0.01},
            headers=HEADERS,
        )

    # Page 1, size 2
    resp = client.get("/pois?page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2

    # Page 3, size 2 (should have 1 item)
    resp = client.get("/pois?page=3&page_size=2", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 1

    # Page beyond total (should have 0 items)
    resp = client.get("/pois?page=10&page_size=2", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 0


def test_get_nonexistent_poi_returns_404(client):
    """Test that getting a non-existent POI returns 404."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/pois/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_update_nonexistent_poi_returns_404(client):
    """Test that updating a non-existent POI returns 404."""
    fake_id = str(uuid.uuid4())
    resp = client.patch(f"/pois/{fake_id}", json={"name": "x"}, headers=HEADERS)
    assert resp.status_code == 404


def test_create_poi_invalid_coordinates(client):
    """Test that invalid coordinates are rejected by Pydantic validation."""
    resp = client.post(
        "/pois",
        json={"name": "Bad POI", "lat": 999, "lon": 2.0},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_readyz_without_real_db(client):
    """In unit-test mode (SQLite), /readyz returns 503 because it checks the real PG engine."""
    resp = client.get("/readyz")
    # /readyz probes the production engine, not the test SQLite — 503 is expected here.
    # In docker-compose integration tests, this returns 200.
    assert resp.status_code in (200, 503)


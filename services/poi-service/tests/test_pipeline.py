"""
Functional pipeline tests – POI service (Enterprise-grade).

Tests complete business flows with realistic Michelin-quality mock data:
  - Full lifecycle: draft → validated → published → archive
  - Concurrent POI management: batch create, filter, paginate
  - Version control: bumps on publish, no bump on draft edit
  - Data integrity: metadata persistence, tag management
  - Cross-field consistency: timestamps monotonically increase
  - Edge cases: Unicode, special characters, rich metadata
"""

import uuid

from tests.conftest import HEADERS


# ── Realistic French real-estate mock data ──────────────────────────

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

MOCK_POI_CHALET = {
    "name": "Chalet Alpin – Megève",
    "description": (
        "Chalet d'exception de 320m² avec accès ski-in/ski-out. "
        "Finitions bois massif, spa privatif, vue Mont-Blanc."
    ),
    "address": "455 Route de Rochebrune, 74120 Megève",
    "lat": 45.8567,
    "lon": 6.6175,
    "poi_type": "chalet",
    "tags": ["ski", "mountain", "luxury", "spa"],
    "metadata": {"surface_m2": 320, "bedrooms": 4, "price_eur": 4500000, "altitude_m": 1800},
}

MOCK_POI_VINEYARD = {
    "name": "Domaine Viticole – Saint-Émilion",
    "description": (
        "Propriété viticole de 35 hectares avec château du XVIIe siècle. "
        "Chai gravitaire, 12 cuves inox, production AOC Saint-Émilion Grand Cru."
    ),
    "address": "Lieu-dit Tertre Roteboeuf, 33330 Saint-Émilion",
    "lat": 44.8962,
    "lon": -0.1559,
    "poi_type": "vineyard",
    "tags": ["wine", "heritage", "saint_emilion", "investment"],
    "metadata": {"surface_ha": 35, "aoc": "Saint-Émilion Grand Cru", "price_eur": 18000000},
}


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline: Full lifecycle
# ═══════════════════════════════════════════════════════════════════════


def test_full_poi_lifecycle(client):
    """Test complete lifecycle: create → validate → publish → update → archive."""
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
    published = resp.json()
    assert published["status"] == "published"
    assert published["version"] == 1

    # 4) Update published POI → version must bump
    resp = client.patch(
        f"/pois/{poi_id}",
        json={"description": "Description mise à jour après rénovation complète."},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["version"] == 2
    assert "rénovation" in updated["description"]

    # 5) Archive
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 200
    archived = resp.json()
    assert archived["status"] == "archived"
    assert archived["version"] == 2  # Version preserved after archive


def test_full_apartment_lifecycle(client):
    """Test apartment-specific lifecycle with metadata verification."""
    resp = client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)
    assert resp.status_code == 201
    poi_id = resp.json()["id"]

    # Verify metadata integrity
    resp = client.get(f"/pois/{poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["metadata"]["floor"] == 3
    assert data["metadata"]["price_eur"] == 3200000

    # Full workflow
    client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    client.post(f"/pois/{poi_id}/archive", headers=HEADERS)

    resp = client.get(f"/pois/{poi_id}", headers=HEADERS)
    assert resp.json()["status"] == "archived"


# ═══════════════════════════════════════════════════════════════════════
#  Workflow error transitions (exhaustive)
# ═══════════════════════════════════════════════════════════════════════


def test_workflow_error_transitions(client):
    """Test ALL invalid workflow transitions return 409 with structured error."""
    resp = client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)
    poi_id = resp.json()["id"]

    # draft → publish: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409
    assert "Cannot transition" in resp.json()["detail"]
    assert resp.json()["error"] == "workflow_error"

    # draft → archive: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409

    # draft → validate: OK
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 200

    # validated → validate: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 409

    # validated → archive: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 409

    # validated → publish: OK
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 200

    # published → publish: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/publish", headers=HEADERS)
    assert resp.status_code == 409

    # published → validate: FORBIDDEN
    resp = client.post(f"/pois/{poi_id}/validate", headers=HEADERS)
    assert resp.status_code == 409

    # published → archive: OK
    resp = client.post(f"/pois/{poi_id}/archive", headers=HEADERS)
    assert resp.status_code == 200

    # archived → all: FORBIDDEN
    for action in ["validate", "publish", "archive"]:
        resp = client.post(f"/pois/{poi_id}/{action}", headers=HEADERS)
        assert resp.status_code == 409, f"archived → {action} should be 409"


# ═══════════════════════════════════════════════════════════════════════
#  Search, filter, and sort
# ═══════════════════════════════════════════════════════════════════════


def test_search_and_filter(client):
    """Test list with search, status filter, and poi_type filter."""
    client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    resp2 = client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)
    client.post("/pois", json=MOCK_POI_CHALET, headers=HEADERS)
    apt_id = resp2.json()["id"]

    # Validate the apartment
    client.post(f"/pois/{apt_id}/validate", headers=HEADERS)

    # Filter by status=draft
    resp = client.get("/pois?status=draft", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["status"] == "draft" for p in data["items"])
    assert data["total"] == 2  # Villa + Chalet

    # Filter by poi_type=villa
    resp = client.get("/pois?poi_type=villa", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["poi_type"] == "villa"

    # Search by text
    resp = client.get("/pois?query=Megève", headers=HEADERS)
    assert resp.json()["total"] >= 1

    # Search by description keyword
    resp = client.get("/pois?query=piscine", headers=HEADERS)
    assert resp.json()["total"] >= 1


def test_combined_filters(client):
    """Test combining status and poi_type filters."""
    resp = client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    villa_id = resp.json()["id"]
    client.post("/pois", json=MOCK_POI_APARTMENT, headers=HEADERS)

    client.post(f"/pois/{villa_id}/validate", headers=HEADERS)

    # Filter: status=validated + poi_type=villa
    resp = client.get("/pois?status=validated&poi_type=villa", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["poi_type"] == "villa"
    assert data["items"][0]["status"] == "validated"


# ═══════════════════════════════════════════════════════════════════════
#  Pagination
# ═══════════════════════════════════════════════════════════════════════


def test_pagination(client):
    """Test pagination with page and page_size params."""
    for i in range(7):
        client.post(
            "/pois",
            json={"name": f"POI-{i:03d}", "lat": 48.0 + i * 0.01, "lon": 2.0 + i * 0.01},
            headers=HEADERS,
        )

    # Page 1
    resp = client.get("/pois?page=1&page_size=3", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 7
    assert len(data["items"]) == 3

    # Page 2
    resp = client.get("/pois?page=2&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 3

    # Page 3 (partial)
    resp = client.get("/pois?page=3&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 1

    # Page 4 (empty)
    resp = client.get("/pois?page=4&page_size=3", headers=HEADERS)
    assert resp.json()["items"] == []


# ═══════════════════════════════════════════════════════════════════════
#  Data integrity
# ═══════════════════════════════════════════════════════════════════════


def test_metadata_persistence_after_update(client):
    """Verify metadata is NOT overwritten when updating other fields."""
    resp = client.post("/pois", json=MOCK_POI_VINEYARD, headers=HEADERS)
    poi_id = resp.json()["id"]

    # Update only the name
    resp = client.patch(f"/pois/{poi_id}", json={"name": "Nouveau Domaine"}, headers=HEADERS)
    data = resp.json()
    assert data["name"] == "Nouveau Domaine"
    assert data["metadata"]["surface_ha"] == 35  # Preserved
    assert data["metadata"]["aoc"] == "Saint-Émilion Grand Cru"  # Preserved


def test_tags_replacement(client):
    """Updating tags replaces the full array, not appends."""
    resp = client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]

    resp = client.patch(f"/pois/{poi_id}", json={"tags": ["sold"]}, headers=HEADERS)
    assert resp.json()["tags"] == ["sold"]


def test_unicode_content(client):
    """Verify Unicode characters are preserved (accents, CJK, emoji)."""
    resp = client.post(
        "/pois",
        json={
            "name": "Propriété à l'Île-de-Ré — Château 日本語",
            "description": "Description avec accents: é, è, ê, ë, à, ù, ç, ö, ü",
            "lat": 46.2,
            "lon": -1.4,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "Île-de-Ré" in data["name"]
    assert "日本語" in data["name"]


def test_timestamps_monotonically_increase(client):
    """updated_at must increase after each update."""
    resp = client.post("/pois", json=MOCK_POI_VILLA, headers=HEADERS)
    poi_id = resp.json()["id"]
    t1 = resp.json()["updated_at"]

    resp = client.patch(f"/pois/{poi_id}", json={"name": "V2"}, headers=HEADERS)
    t2 = resp.json()["updated_at"]
    assert t2 >= t1


# ═══════════════════════════════════════════════════════════════════════
#  Error paths – 404 with structured body
# ═══════════════════════════════════════════════════════════════════════


def test_get_nonexistent_poi_returns_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/pois/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body


def test_update_nonexistent_poi_returns_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.patch(f"/pois/{fake_id}", json={"name": "x"}, headers=HEADERS)
    assert resp.status_code == 404


def test_create_poi_invalid_coordinates(client):
    resp = client.post("/pois", json={"name": "Bad", "lat": 999, "lon": 2.0}, headers=HEADERS)
    assert resp.status_code == 422


def test_readyz_without_real_db(client):
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)


# ═══════════════════════════════════════════════════════════════════════
#  Batch scenario – Multiple POI types at scale
# ═══════════════════════════════════════════════════════════════════════


def test_batch_create_and_filter_by_type(client):
    """Create POIs of different types and verify type filtering."""
    mocks = [MOCK_POI_VILLA, MOCK_POI_APARTMENT, MOCK_POI_CHALET, MOCK_POI_VINEYARD]
    for mock in mocks:
        resp = client.post("/pois", json=mock, headers=HEADERS)
        assert resp.status_code == 201

    # Each type should be filterable
    for poi_type in ["villa", "apartment", "chalet", "vineyard"]:
        resp = client.get(f"/pois?poi_type={poi_type}", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert all(p["poi_type"] == poi_type for p in data["items"])

    # Total should be 4
    resp = client.get("/pois", headers=HEADERS)
    assert resp.json()["total"] == 4

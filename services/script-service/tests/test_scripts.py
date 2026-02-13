"""
Enterprise-grade unit tests – Script Service.

Coverage:
  - Script generation: full schema validation, scenes structure, narration
  - Mocked upstream services: POI + Asset HTTP clients
  - Listing and pagination
  - Error paths: POI not found, auth, 404 on get
  - Schema response validation: all fields present
  - Multiple scripts for same POI
  - NLP provider stub verification

Mock data: realistic French property with rich context.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Mock HTTP responses (upstream services)
# ═══════════════════════════════════════════════════════════════════════

MOCK_POI_ID = str(uuid.uuid4())

MOCK_POI_RESPONSE_DATA = {
    "id": MOCK_POI_ID,
    "name": "Villa Paradiso – Les Baux-de-Provence",
    "description": (
        "Propriété d'exception de 450m² sur un terrain arboré de 2 hectares. "
        "5 chambres, piscine à débordement, vue panoramique sur les Alpilles."
    ),
    "address": "Route de Maussane, 13520 Les Baux-de-Provence",
    "lat": 43.7439,
    "lon": 4.7953,
    "poi_type": "villa",
    "tags": ["luxury", "pool", "provence"],
    "status": "published",
}

MOCK_ASSETS_RESPONSE_DATA = {
    "items": [
        {"id": str(uuid.uuid4()), "name": "facade-drone.jpg", "asset_type": "photo"},
        {"id": str(uuid.uuid4()), "name": "salon-panorama.jpg", "asset_type": "photo"},
        {"id": str(uuid.uuid4()), "name": "visite-4k.mp4", "asset_type": "raw_video"},
        {"id": str(uuid.uuid4()), "name": "plan-rdc.pdf", "asset_type": "floor_plan"},
    ],
    "total": 4,
}


def _mock_poi_response(status_code: int = 200, data: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data or MOCK_POI_RESPONSE_DATA
    return resp


def _mock_assets_response(status_code: int = 200, data: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data or MOCK_ASSETS_RESPONSE_DATA
    return resp


# ═══════════════════════════════════════════════════════════════════════
#  Schema helpers
# ═══════════════════════════════════════════════════════════════════════

SCRIPT_RESPONSE_FIELDS = [
    "id", "poi_id", "title", "tone", "total_duration_seconds",
    "scenes", "narration_text", "nlp_provider", "metadata",
    "version", "created_at",
]


def _assert_script_schema(data: dict) -> None:
    """Assert all fields present in Script response."""
    for field in SCRIPT_RESPONSE_FIELDS:
        assert field in data, f"Missing field '{field}' in Script response"
    assert isinstance(data["id"], str) and len(data["id"]) == 36
    assert isinstance(data["scenes"], list)
    assert isinstance(data["metadata"], dict)
    assert isinstance(data["version"], int)
    assert data["tone"] in ("warm", "professional", "cinematic")


# ═══════════════════════════════════════════════════════════════════════
#  GENERATE – Happy path
# ═══════════════════════════════════════════════════════════════════════


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_full_schema(mock_poi, mock_asset, mock_kafka, client):
    """Generate script – verify full response schema and content."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    _assert_script_schema(data)

    # Content assertions
    assert data["title"].startswith("Video Script")
    assert data["tone"] == "warm"
    assert data["total_duration_seconds"] == 30.0
    assert data["nlp_provider"] == "stub"
    assert data["narration_text"] is not None
    assert len(data["narration_text"]) > 10
    assert data["version"] == 1

    # Scenes structure
    assert len(data["scenes"]) == 6
    for i, scene in enumerate(data["scenes"]):
        assert "scene_number" in scene
        assert "title" in scene
        assert "description" in scene
        assert "duration_seconds" in scene
        assert scene["scene_number"] == i + 1
        assert scene["duration_seconds"] == 5.0

    # Metadata includes POI context
    assert "poi_name" in data["metadata"]
    assert "asset_count" in data["metadata"]
    assert data["metadata"]["asset_count"] == 4


@patch("app.services.script_service.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_publishes_kafka_event(mock_poi, mock_asset, mock_kafka, client):
    """Verify Kafka event is published after script generation."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 201
    mock_kafka.assert_called_once()


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_no_assets(mock_poi, mock_asset, mock_kafka, client):
    """Generate script when POI has no assets – should still work."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response(data={"items": [], "total": 0}))

    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["metadata"]["asset_count"] == 0
    assert len(data["scenes"]) == 6  # Stub always generates 6 scenes


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_assets_service_error(mock_poi, mock_asset, mock_kafka, client):
    """Asset service returns 500 – script should still generate (graceful degradation)."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    error_resp = MagicMock(spec=httpx.Response)
    error_resp.status_code = 500
    mock_asset.get = AsyncMock(return_value=error_resp)

    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 201
    assert resp.json()["metadata"]["asset_count"] == 0


# ═══════════════════════════════════════════════════════════════════════
#  GENERATE – Error paths
# ═══════════════════════════════════════════════════════════════════════


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_poi_not_found(mock_poi, mock_asset, mock_kafka, client):
    """POI 404 → script generation should fail with 400."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response(status_code=404))

    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 400


def test_generate_script_missing_poi_id(client):
    """Missing poi_id query param → 422."""
    resp = client.post("/scripts/generate", headers=HEADERS)
    assert resp.status_code == 422


def test_generate_script_invalid_poi_id(client):
    """Invalid UUID format → 422."""
    resp = client.post("/scripts/generate?poi_id=not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  LIST / GET
# ═══════════════════════════════════════════════════════════════════════


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_list_scripts_by_poi_id(mock_poi, mock_asset, mock_kafka, client):
    """List scripts filtered by poi_id."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    # Generate 2 scripts for same POI
    for _ in range(2):
        resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
        assert resp.status_code == 201

    resp = client.get(f"/scripts?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert all(s["poi_id"] == poi_id for s in data["items"])


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_list_scripts_pagination(mock_poi, mock_asset, mock_kafka, client):
    """Test pagination on script listing."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    for _ in range(5):
        client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)

    resp = client.get(f"/scripts?poi_id={poi_id}&page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp = client.get(f"/scripts?poi_id={poi_id}&page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1


def test_list_scripts_empty(client):
    resp = client.get("/scripts", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_get_script_by_id(mock_poi, mock_asset, mock_kafka, client):
    """Get specific script by ID."""
    mock_poi.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    script_id = resp.json()["id"]

    resp = client.get(f"/scripts/{script_id}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    _assert_script_schema(data)
    assert data["id"] == script_id


def test_get_script_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/scripts/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body


def test_get_script_invalid_uuid(client):
    resp = client.get("/scripts/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422


def test_list_scripts_page_size_max(client):
    """page_size > 100 should be rejected."""
    resp = client.get("/scripts?page_size=101", headers=HEADERS)
    assert resp.status_code == 422


def test_list_scripts_page_zero_rejected(client):
    resp = client.get("/scripts?page=0", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════════════


def test_auth_required_list(client):
    resp = client.get("/scripts")
    assert resp.status_code == 401


def test_auth_required_generate(client):
    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}")
    assert resp.status_code == 401


def test_auth_wrong_key(client):
    resp = client.get("/scripts", headers={"X-API-Key": "wrong"})
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

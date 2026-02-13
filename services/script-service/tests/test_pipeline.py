"""
Functional pipeline tests – Script service.

Tests script generation with realistic mock POI/asset data,
verifying the NLP stub output structure and event publishing.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from tests.conftest import HEADERS


# ── Mock data (realistic Michelin-quality POI + Assets) ───────────────────


def _mock_poi_response(poi_id: str):
    """Return a mock httpx.Response for a realistic published POI."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "id": poi_id,
        "name": "Villa Paradiso – Les Baux-de-Provence",
        "description": (
            "Propriété d'exception de 450m² sur un terrain arboré de 2 hectares. "
            "5 chambres, piscine à débordement, vue sur les Alpilles."
        ),
        "address": "Route de Maussane, 13520 Les Baux-de-Provence",
        "lat": 43.7439,
        "lon": 4.7953,
        "poi_type": "villa",
        "tags": ["luxury", "pool", "provence"],
        "status": "published",
        "version": 1,
    }
    return resp


def _mock_assets_response():
    """Return a mock httpx.Response for realistic assets."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "items": [
            {
                "id": str(uuid.uuid4()),
                "name": "facade_principale.jpg",
                "asset_type": "photo",
                "description": "Vue de la façade principale",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "piscine_drone.jpg",
                "asset_type": "photo",
                "description": "Vue aérienne de la piscine",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "visite_raw.mp4",
                "asset_type": "raw_video",
                "description": "Captation vidéo brute de la visite",
            },
        ],
        "total": 3,
    }
    return resp


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_full_script_generation(mock_poi, mock_asset, mock_kafka, client):
    """Test complete script generation pipeline with realistic data."""
    poi_id = str(uuid.uuid4())
    mock_poi.get = AsyncMock(return_value=_mock_poi_response(poi_id))
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    # Generate script
    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 201

    script = resp.json()
    assert script["poi_id"] == poi_id
    assert "Video Script" in script["title"]
    assert script["tone"] == "warm"
    assert script["total_duration_seconds"] == 30.0
    assert script["nlp_provider"] == "stub"
    assert script["version"] == 1

    # Verify scene structure
    scenes = script["scenes"]
    assert len(scenes) == 6
    for scene in scenes:
        assert "scene_number" in scene
        assert "title" in scene
        assert "visual_prompt" in scene
        assert "duration_seconds" in scene

    # Verify narration text is present
    assert script["narration_text"] is not None
    assert len(script["narration_text"]) > 50

    # Verify metadata
    assert script["metadata"]["poi_name"] == "Villa Paradiso – Les Baux-de-Provence"
    assert script["metadata"]["asset_count"] == 3

    # Verify script is persisted and can be fetched
    script_id = script["id"]
    resp = client.get(f"/scripts/{script_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == script_id


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_script_listing_by_poi(mock_poi, mock_asset, mock_kafka, client):
    """Generate 2 scripts for the same POI and verify listing."""
    poi_id = str(uuid.uuid4())
    mock_poi.get = AsyncMock(return_value=_mock_poi_response(poi_id))
    mock_asset.get = AsyncMock(return_value=_mock_assets_response())

    # Generate 2 scripts
    for _ in range(2):
        resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
        assert resp.status_code == 201

    # List by poi_id
    resp = client.get(f"/scripts?poi_id={poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 2
    assert all(s["poi_id"] == poi_id for s in data["items"])


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_script_generation_with_empty_assets(mock_poi, mock_asset, mock_kafka, client):
    """Test script generation when POI has no assets."""
    poi_id = str(uuid.uuid4())
    mock_poi.get = AsyncMock(return_value=_mock_poi_response(poi_id))

    empty_assets = MagicMock(spec=httpx.Response)
    empty_assets.status_code = 200
    empty_assets.json.return_value = {"items": [], "total": 0}
    mock_asset.get = AsyncMock(return_value=empty_assets)

    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 201
    assert resp.json()["metadata"]["asset_count"] == 0


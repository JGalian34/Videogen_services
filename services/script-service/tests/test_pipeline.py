"""
Functional pipeline tests – Script Service (Enterprise-grade).

Tests the complete script generation flow with realistic mock data:
  - End-to-end: fetch POI → fetch assets → generate NLP → persist → publish event
  - Multiple scripts per POI (version tracking)
  - Scene structure integrity verification
  - Narration text quality checks
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from tests.conftest import HEADERS


# ── Mock upstream service responses ─────────────────────────────────

MOCK_POI_VILLA = {
    "id": str(uuid.uuid4()),
    "name": "Villa Paradiso – Les Baux-de-Provence",
    "description": (
        "Propriété d'exception de 450m² sur un terrain arboré de 2 hectares. "
        "5 chambres, piscine à débordement, vue panoramique sur les Alpilles. "
        "Prestations haut de gamme : domotique, cave à vin, garage 3 places."
    ),
    "address": "Route de Maussane, 13520 Les Baux-de-Provence",
    "lat": 43.7439,
    "lon": 4.7953,
    "poi_type": "villa",
    "tags": ["luxury", "pool", "provence", "panoramic_view"],
    "status": "published",
}

MOCK_VILLA_ASSETS = {
    "items": [
        {"id": str(uuid.uuid4()), "name": "facade-drone.jpg", "asset_type": "photo"},
        {"id": str(uuid.uuid4()), "name": "salon-panorama.jpg", "asset_type": "photo"},
        {"id": str(uuid.uuid4()), "name": "piscine-sunset.jpg", "asset_type": "photo"},
        {"id": str(uuid.uuid4()), "name": "visite-4k.mp4", "asset_type": "raw_video"},
        {"id": str(uuid.uuid4()), "name": "plan-rdc.pdf", "asset_type": "floor_plan"},
        {"id": str(uuid.uuid4()), "name": "dpe-classe-a.pdf", "asset_type": "document"},
    ],
    "total": 6,
}


def _mock_resp(status_code: int, data: dict):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json.return_value = data
    return r


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline: Full script generation
# ═══════════════════════════════════════════════════════════════════════


@patch("app.services.script_service.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_full_script_generation_pipeline(mock_poi, mock_asset, mock_kafka, client):
    """Generate a complete video script from POI + assets → verify all outputs."""
    mock_poi.get = AsyncMock(return_value=_mock_resp(200, MOCK_POI_VILLA))
    mock_asset.get = AsyncMock(return_value=_mock_resp(200, MOCK_VILLA_ASSETS))

    poi_id = str(uuid.uuid4())

    # 1) Generate script
    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 201
    script = resp.json()
    script_id = script["id"]

    # 2) Verify script structure
    assert script["poi_id"] == poi_id
    assert script["tone"] == "warm"
    assert script["total_duration_seconds"] == 30.0
    assert script["nlp_provider"] == "stub"
    assert script["version"] == 1

    # 3) Verify scenes (stub generates 6)
    scenes = script["scenes"]
    assert len(scenes) == 6
    total_duration = sum(s["duration_seconds"] for s in scenes)
    assert total_duration == 30.0

    # Scenes are numbered sequentially
    for i, scene in enumerate(scenes):
        assert scene["scene_number"] == i + 1
        assert len(scene["title"]) > 0
        assert len(scene["description"]) > 0

    # 4) Verify narration text
    assert script["narration_text"] is not None
    assert len(script["narration_text"]) > 20

    # 5) Verify metadata context
    assert script["metadata"]["poi_name"] == "Villa Paradiso – Les Baux-de-Provence"
    assert script["metadata"]["asset_count"] == 6

    # 6) Verify persistence – get by ID
    resp = client.get(f"/scripts/{script_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == script_id

    # 7) Verify persistence – list by poi_id
    resp = client.get(f"/scripts?poi_id={poi_id}", headers=HEADERS)
    assert resp.json()["total"] == 1

    # 8) Verify Kafka event published
    mock_kafka.assert_called_once()


@patch("app.services.script_service.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_multiple_scripts_for_same_poi(mock_poi, mock_asset, mock_kafka, client):
    """Generate multiple scripts for the same POI – all coexist."""
    mock_poi.get = AsyncMock(return_value=_mock_resp(200, MOCK_POI_VILLA))
    mock_asset.get = AsyncMock(return_value=_mock_resp(200, MOCK_VILLA_ASSETS))

    poi_id = str(uuid.uuid4())
    script_ids = []

    for _ in range(3):
        resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
        assert resp.status_code == 201
        script_ids.append(resp.json()["id"])

    # All 3 scripts exist
    resp = client.get(f"/scripts?poi_id={poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 3
    returned_ids = {s["id"] for s in data["items"]}
    assert set(script_ids) == returned_ids

    # Each script has unique ID
    assert len(set(script_ids)) == 3

"""Tests: Script generation with mocked HTTP clients."""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from tests.conftest import HEADERS


def _mock_poi_response():
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Test Villa",
        "description": "Beautiful villa",
        "address": "123 Test St, Paris",
        "lat": 48.8566,
        "lon": 2.3522,
        "poi_type": "villa",
        "tags": ["luxury"],
        "status": "published",
    }
    return resp


def _mock_assets_response():
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "items": [
            {"id": str(uuid.uuid4()), "name": "photo1.jpg", "asset_type": "photo"},
            {"id": str(uuid.uuid4()), "name": "video1.mp4", "asset_type": "raw_video"},
        ],
        "total": 2,
    }
    return resp


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script(mock_poi_client, mock_asset_client, mock_kafka, client):
    mock_poi_client.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset_client.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    resp = client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 201

    data = resp.json()
    assert data["title"].startswith("Video Script")
    assert len(data["scenes"]) == 6
    assert data["tone"] == "warm"
    assert data["total_duration_seconds"] == 30.0
    assert data["narration_text"] is not None
    assert data["nlp_provider"] == "stub"


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_list_scripts(mock_poi_client, mock_asset_client, mock_kafka, client):
    mock_poi_client.get = AsyncMock(return_value=_mock_poi_response())
    mock_asset_client.get = AsyncMock(return_value=_mock_assets_response())

    poi_id = str(uuid.uuid4())
    client.post(f"/scripts/generate?poi_id={poi_id}", headers=HEADERS)

    resp = client.get(f"/scripts?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200


# ── Error tests ────────────────────────────────────────────────────

def test_get_script_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/scripts/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
@patch("app.services.script_service._asset_client")
@patch("app.services.script_service._poi_client")
def test_generate_script_poi_not_found(mock_poi_client, mock_asset_client, mock_kafka, client):
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.status_code = 404
    mock_poi_client.get = AsyncMock(return_value=bad_resp)

    resp = client.post(f"/scripts/generate?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 400


def test_missing_api_key(client):
    resp = client.get("/scripts")
    assert resp.status_code == 401


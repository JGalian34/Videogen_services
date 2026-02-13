"""Tests: Render service – consume script.generated event + API."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from tests.conftest import HEADERS


@pytest.mark.asyncio
@patch("app.integrations.kafka_producer.publish_video_event", new_callable=AsyncMock)
async def test_create_render_from_event(mock_kafka, db):
    """Simulate consuming a script.generated event."""
    from app.services.render_service import RenderService

    svc = RenderService(db)
    payload = {
        "script_id": str(uuid.uuid4()),
        "poi_id": str(uuid.uuid4()),
        "scene_count": 3,
        "scenes": [
            {"scene_number": 1, "title": "Establishing", "visual_prompt": "Aerial view", "duration_seconds": 5.0},
            {"scene_number": 2, "title": "Interior", "visual_prompt": "Walk-through", "duration_seconds": 5.0},
            {"scene_number": 3, "title": "Closing", "visual_prompt": "Sunset", "duration_seconds": 5.0},
        ],
    }

    job = await svc.create_render_from_script_event(payload)

    assert job.status == "completed"
    assert job.total_scenes == 3
    assert job.completed_scenes == 3
    assert len(job.scenes) == 3


def test_list_renders_empty(client):
    resp = client.get("/renders", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200


# ── Error tests ────────────────────────────────────────────────────


def test_get_render_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/renders/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_retry_render_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/renders/retry/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404


def test_missing_api_key(client):
    resp = client.get("/renders")
    assert resp.status_code == 401

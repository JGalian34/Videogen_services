"""
Functional pipeline tests – Render Service (Enterprise-grade).

Tests the complete render lifecycle:
  - Event → create render → process all scenes → completed
  - Voiceover attachment → video publication → CDN URL generation
  - Multi-render pipeline for different POIs
  - Full pipeline: render → voiceover → publish
  - Error recovery: failed render → retry
  - Idempotent consumption check
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Mock data
# ═══════════════════════════════════════════════════════════════════════


def _make_script_event(poi_id: str | None = None, scene_count: int = 3) -> dict:
    return {
        "script_id": str(uuid.uuid4()),
        "poi_id": poi_id or str(uuid.uuid4()),
        "scene_count": scene_count,
        "scenes": [
            {
                "scene_number": i + 1,
                "title": f"Scène {i + 1}",
                "visual_prompt": f"Visual prompt for scene {i + 1}",
                "duration_seconds": 5.0,
            }
            for i in range(scene_count)
        ],
    }


async def _create_render_from_event(db, event: dict):
    """Helper to create a render job via service layer."""
    from app.services.render_service import RenderService

    svc = RenderService(db)
    return await svc.create_render_from_script_event(event)


# ═══════════════════════════════════════════════════════════════════════
#  Full pipeline: render → voiceover → publish
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@patch("app.services.render_service.publish_video_event", new_callable=AsyncMock)
async def test_full_render_pipeline(mock_kafka, db):
    """Complete flow: event → render → voiceover → publish → CDN URL."""
    from app.services.render_service import RenderService

    # 1) Create render from event
    event = _make_script_event(scene_count=4)
    job = await _create_render_from_event(db, event)

    assert job.status == "completed"
    assert job.total_scenes == 4
    assert job.completed_scenes == 4
    assert len(job.scenes) == 4
    assert job.output_path is not None

    # 2) Attach voiceover
    svc = RenderService(db)
    voiceover_id = str(uuid.uuid4())
    audio_path = "/data/voiceovers/narration-fr-hd.mp3"
    job = await svc.attach_voiceover(job.id, voiceover_id, audio_path)

    assert job.voiceover_id == voiceover_id
    assert job.voiceover_audio_path == audio_path

    # 3) Publish video
    job = await svc.publish_video(job.id)

    assert job.published_url is not None
    assert "cdn.poi-video.example.com" in job.published_url
    assert str(job.id) in job.published_url
    assert job.published_at is not None

    # Kafka events: 4 scene + 1 render_completed + 1 video_published
    assert mock_kafka.call_count >= 6


@pytest.mark.asyncio
@patch("app.services.render_service.publish_video_event", new_callable=AsyncMock)
async def test_multi_poi_render_pipeline(mock_kafka, db):
    """Create renders for multiple POIs and verify isolation."""
    poi_a = str(uuid.uuid4())
    poi_b = str(uuid.uuid4())

    # 2 renders for POI A
    await _create_render_from_event(db, _make_script_event(poi_id=poi_a, scene_count=2))
    await _create_render_from_event(db, _make_script_event(poi_id=poi_a, scene_count=3))

    # 1 render for POI B
    await _create_render_from_event(db, _make_script_event(poi_id=poi_b, scene_count=5))

    from app.services.render_service import RenderService

    svc = RenderService(db)

    items_a, total_a = svc.list_renders(poi_id=uuid.UUID(poi_a))
    assert total_a == 2
    assert all(str(j.poi_id) == poi_a for j in items_a)

    items_b, total_b = svc.list_renders(poi_id=uuid.UUID(poi_b))
    assert total_b == 1
    assert items_b[0].total_scenes == 5


@pytest.mark.asyncio
@patch("app.services.render_service.publish_video_event", new_callable=AsyncMock)
async def test_render_scene_data_integrity(mock_kafka, db):
    """Verify scene-level data integrity after rendering."""
    event = _make_script_event(scene_count=5)
    job = await _create_render_from_event(db, event)

    sorted_scenes = sorted(job.scenes, key=lambda s: s.scene_number)

    # Scene numbers are sequential 1..5
    scene_numbers = [s.scene_number for s in sorted_scenes]
    assert scene_numbers == [1, 2, 3, 4, 5]

    # All scenes completed
    for scene in sorted_scenes:
        assert scene.status == "completed"
        assert scene.output_path is not None
        assert scene.provider == "stub"

    # Total duration is consistent
    total_duration = sum(s.duration_seconds for s in sorted_scenes)
    assert total_duration == 25.0  # 5 scenes × 5.0s


@pytest.mark.asyncio
@patch("app.services.render_service.publish_video_event", new_callable=AsyncMock)
async def test_error_recovery_pipeline(mock_kafka, db):
    """Create a failed render, retry it, verify state reset."""
    from app.db.models import RenderJob
    from app.services.render_service import RenderService

    # Create a "failed" render manually
    failed_job = RenderJob(
        poi_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        status="failed",
        total_scenes=4,
        completed_scenes=2,
        error_message="Runway API rate limit exceeded on scene 3",
    )
    db.add(failed_job)
    db.commit()
    db.refresh(failed_job)

    svc = RenderService(db)

    # Retry
    job = await svc.retry_render(failed_job.id)
    assert job.status == "pending"
    assert job.completed_scenes == 0
    assert job.error_message is None


@pytest.mark.asyncio
@patch("app.services.render_service.publish_video_event", new_callable=AsyncMock)
async def test_publish_without_voiceover(mock_kafka, db):
    """Publishing without attaching voiceover should still work."""
    event = _make_script_event(scene_count=2)
    job = await _create_render_from_event(db, event)

    from app.services.render_service import RenderService

    svc = RenderService(db)
    job = await svc.publish_video(job.id)

    assert job.published_url is not None
    assert job.voiceover_id is None  # No voiceover attached


# ═══════════════════════════════════════════════════════════════════════
#  API-level pipeline tests
# ═══════════════════════════════════════════════════════════════════════


def test_list_renders_pagination(client):
    """Pagination boundary tests on empty database."""
    # Page 1, default page_size
    resp = client.get("/renders?page=1&page_size=10", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_render_404_error_body(client):
    """404 returns structured error body."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/renders/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body
    assert fake_id in body["detail"]

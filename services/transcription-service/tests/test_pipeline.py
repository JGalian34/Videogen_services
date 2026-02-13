"""
Functional pipeline tests – Transcription service.

Tests the complete transcription lifecycle with realistic mock data:
  start transcription → stub worker → completed with segments.
"""

import uuid

from tests.conftest import HEADERS


def test_full_transcription_pipeline(client):
    """Test complete transcription flow: create → process → completed."""
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    # Start transcription
    resp = client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()

    # Stub completes immediately
    assert data["status"] == "completed"
    assert data["poi_id"] == poi_id
    assert data["asset_video_id"] == asset_id

    # Verify transcription quality
    assert data["text"] is not None
    assert len(data["text"]) > 20
    assert data["confidence"] == 0.95
    assert data["duration_seconds"] == 12.5

    # Verify segments
    segments = data["segments"]
    assert len(segments) == 3
    for seg in segments:
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg
        assert seg["end"] > seg["start"]

    # Verify ordering (segments are chronological)
    for i in range(len(segments) - 1):
        assert segments[i]["end"] <= segments[i + 1]["start"]

    # Verify persistence
    tid = data["id"]
    resp = client.get(f"/transcriptions/{tid}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == tid
    assert resp.json()["status"] == "completed"


def test_multiple_transcriptions_for_poi(client):
    """Create multiple transcriptions for the same POI (different videos)."""
    poi_id = str(uuid.uuid4())
    video_ids = [str(uuid.uuid4()) for _ in range(3)]

    for vid in video_ids:
        resp = client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={vid}",
            headers=HEADERS,
        )
        assert resp.status_code == 201

    # List all transcriptions for this POI
    resp = client.get(f"/transcriptions?poi_id={poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert all(t["poi_id"] == poi_id for t in data["items"])


def test_transcription_pagination(client):
    """Test pagination on transcription listing."""
    poi_id = str(uuid.uuid4())

    # Create 5 transcriptions
    for _ in range(5):
        client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )

    # Page 1, size 2
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    # Page 3
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1


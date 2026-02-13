"""
Functional pipeline tests – Transcription Service (Enterprise-grade).

Tests the complete transcription lifecycle with realistic mock data:
  - Start transcription → stub worker → completed with segments
  - Multiple transcriptions for same POI (multi-video property)
  - Data integrity: segments cover full duration
  - French content quality verification
  - Pagination across multiple transcriptions
"""

import uuid

from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Full transcription pipeline
# ═══════════════════════════════════════════════════════════════════════


def test_full_transcription_pipeline(client):
    """Complete flow: create → process → verify quality → persist → retrieve."""
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    # 1) Start transcription
    resp = client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    tid = data["id"]

    # 2) Status should be completed (stub worker is synchronous)
    assert data["status"] == "completed"
    assert data["poi_id"] == poi_id
    assert data["asset_video_id"] == asset_id

    # 3) Verify transcription text quality
    assert data["text"] is not None
    assert len(data["text"]) > 20
    # French content expected from stub
    text_lower = data["text"].lower()
    assert any(word in text_lower for word in ["bienvenue", "visite", "bien", "exception"])

    # 4) Confidence and duration
    assert data["confidence"] == 0.95
    assert data["duration_seconds"] == 12.5

    # 5) Segments integrity
    segments = data["segments"]
    assert len(segments) == 3

    # Segments are chronologically ordered
    for i in range(len(segments) - 1):
        assert segments[i]["end"] <= segments[i + 1]["start"]

    # First segment starts at 0, last ends at duration
    assert segments[0]["start"] == 0.0
    assert segments[-1]["end"] == data["duration_seconds"]

    # Each segment has meaningful text
    for seg in segments:
        assert len(seg["text"]) > 5

    # 6) Persistence: retrieve by ID
    resp = client.get(f"/transcriptions/{tid}", headers=HEADERS)
    assert resp.status_code == 200
    retrieved = resp.json()
    assert retrieved["id"] == tid
    assert retrieved["status"] == "completed"
    assert retrieved["text"] == data["text"]

    # 7) Persistence: list by poi_id
    resp = client.get(f"/transcriptions?poi_id={poi_id}", headers=HEADERS)
    assert resp.json()["total"] == 1


def test_multi_video_property_transcriptions(client):
    """Create transcriptions for multiple videos of the same property."""
    poi_id = str(uuid.uuid4())
    video_descriptions = [
        "visite-virtuelle-4k.mp4",
        "drone-aerien-hd.mp4",
        "interview-proprietaire.mp4",
        "time-lapse-renovation.mp4",
    ]

    transcript_ids = []
    for desc in video_descriptions:
        resp = client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )
        assert resp.status_code == 201
        transcript_ids.append(resp.json()["id"])

    # All 4 transcriptions exist
    resp = client.get(f"/transcriptions?poi_id={poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 4
    assert all(t["poi_id"] == poi_id for t in data["items"])
    assert all(t["status"] == "completed" for t in data["items"])

    # All IDs are unique
    assert len(set(transcript_ids)) == 4


def test_transcription_isolation_between_pois(client):
    """Transcriptions from POI A should not appear in POI B listing."""
    poi_a = str(uuid.uuid4())
    poi_b = str(uuid.uuid4())

    # 3 transcriptions for POI A
    for _ in range(3):
        client.post(
            f"/transcriptions/start?poi_id={poi_a}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )

    # 1 transcription for POI B
    client.post(
        f"/transcriptions/start?poi_id={poi_b}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )

    resp = client.get(f"/transcriptions?poi_id={poi_a}", headers=HEADERS)
    assert resp.json()["total"] == 3

    resp = client.get(f"/transcriptions?poi_id={poi_b}", headers=HEADERS)
    assert resp.json()["total"] == 1


def test_transcription_pagination_pipeline(client):
    """Create many transcriptions, paginate through them."""
    poi_id = str(uuid.uuid4())

    for _ in range(7):
        client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )

    # Page 1: 3 items
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=1&page_size=3", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 7
    assert len(data["items"]) == 3

    # Page 2: 3 items
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=2&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 3

    # Page 3: 1 item
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=3&page_size=3", headers=HEADERS)
    assert len(resp.json()["items"]) == 1

    # Page 4: 0 items
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=4&page_size=3", headers=HEADERS)
    assert resp.json()["items"] == []

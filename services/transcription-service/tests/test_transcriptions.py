"""
Enterprise-grade unit tests – Transcription Service.

Coverage:
  - Start transcription: stub worker runs to completion
  - Schema response validation: all fields, segments structure
  - Listing with pagination and poi_id filter
  - Error paths: 404, 422, auth
  - Segment chronological ordering
  - Multiple transcriptions per POI
  - Health / readiness

Mock data: realistic French property video transcriptions.
"""

import uuid

from tests.conftest import HEADERS


# ═══════════════════════════════════════════════════════════════════════
#  Schema helpers
# ═══════════════════════════════════════════════════════════════════════

TRANSCRIPTION_FIELDS = [
    "id", "poi_id", "asset_video_id", "status", "language",
    "text", "confidence", "duration_seconds", "segments",
    "error_message", "metadata", "created_at", "completed_at",
]


def _assert_transcription_schema(data: dict) -> None:
    """Assert all required fields present in Transcription response."""
    for field in TRANSCRIPTION_FIELDS:
        assert field in data, f"Missing field '{field}' in Transcription response"
    assert isinstance(data["id"], str) and len(data["id"]) == 36
    assert isinstance(data["metadata"], dict)
    assert data["status"] in ("pending", "processing", "completed", "failed")


# ═══════════════════════════════════════════════════════════════════════
#  START – Happy path
# ═══════════════════════════════════════════════════════════════════════


def test_start_transcription_full_schema(client):
    """Start transcription – verify complete response schema."""
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    resp = client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    _assert_transcription_schema(data)
    assert data["poi_id"] == poi_id
    assert data["asset_video_id"] == asset_id
    assert data["status"] == "completed"  # Stub completes immediately
    assert data["language"] == "fr"
    assert data["error_message"] is None


def test_transcription_text_content(client):
    """Verify transcription text is non-empty and meaningful."""
    resp = client.post(
        f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    data = resp.json()
    assert data["text"] is not None
    assert len(data["text"]) > 20
    assert "visite" in data["text"].lower()  # French content


def test_transcription_confidence_and_duration(client):
    """Verify confidence score and duration are set."""
    resp = client.post(
        f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    data = resp.json()
    assert data["confidence"] == 0.95
    assert 0.0 < data["confidence"] <= 1.0
    assert data["duration_seconds"] == 12.5
    assert data["duration_seconds"] > 0


def test_transcription_segments_structure(client):
    """Verify segments are properly structured and chronological."""
    resp = client.post(
        f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    data = resp.json()
    segments = data["segments"]

    assert len(segments) == 3
    for seg in segments:
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg
        assert isinstance(seg["start"], (int, float))
        assert isinstance(seg["end"], (int, float))
        assert seg["end"] > seg["start"]
        assert len(seg["text"]) > 0

    # Chronological ordering
    for i in range(len(segments) - 1):
        assert segments[i]["end"] <= segments[i + 1]["start"]

    # First segment starts at 0
    assert segments[0]["start"] == 0.0


def test_transcription_completed_at_set(client):
    """completed_at must be set for completed transcriptions."""
    resp = client.post(
        f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    data = resp.json()
    assert data["completed_at"] is not None


def test_transcription_unique_ids(client):
    """Each transcription gets a unique ID."""
    ids = set()
    for _ in range(3):
        resp = client.post(
            f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )
        assert resp.status_code == 201
        ids.add(resp.json()["id"])
    assert len(ids) == 3


# ═══════════════════════════════════════════════════════════════════════
#  START – Validation errors (422)
# ═══════════════════════════════════════════════════════════════════════


def test_start_transcription_missing_all_params(client):
    resp = client.post("/transcriptions/start", headers=HEADERS)
    assert resp.status_code == 422


def test_start_transcription_missing_asset_id(client):
    resp = client.post(f"/transcriptions/start?poi_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 422


def test_start_transcription_missing_poi_id(client):
    resp = client.post(f"/transcriptions/start?asset_video_id={uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 422


def test_start_transcription_invalid_uuid(client):
    resp = client.post("/transcriptions/start?poi_id=bad&asset_video_id=bad", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  GET
# ═══════════════════════════════════════════════════════════════════════


def test_get_transcription_by_id(client):
    resp = client.post(
        f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    tid = resp.json()["id"]

    resp = client.get(f"/transcriptions/{tid}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    _assert_transcription_schema(data)
    assert data["id"] == tid


def test_get_transcription_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/transcriptions/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "detail" in body


def test_get_transcription_invalid_uuid(client):
    resp = client.get("/transcriptions/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  LIST + PAGINATION
# ═══════════════════════════════════════════════════════════════════════


def test_list_transcriptions_empty(client):
    resp = client.get("/transcriptions", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_transcriptions_by_poi_id(client):
    poi_id = str(uuid.uuid4())
    other_poi = str(uuid.uuid4())

    # 2 for our POI
    for _ in range(2):
        client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )
    # 1 for another POI
    client.post(
        f"/transcriptions/start?poi_id={other_poi}&asset_video_id={uuid.uuid4()}",
        headers=HEADERS,
    )

    resp = client.get(f"/transcriptions?poi_id={poi_id}", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 2
    assert all(t["poi_id"] == poi_id for t in data["items"])


def test_list_transcriptions_pagination(client):
    poi_id = str(uuid.uuid4())
    for _ in range(5):
        client.post(
            f"/transcriptions/start?poi_id={poi_id}&asset_video_id={uuid.uuid4()}",
            headers=HEADERS,
        )

    # Page 1
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=1&page_size=2", headers=HEADERS)
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2

    # Page 3 (partial)
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=3&page_size=2", headers=HEADERS)
    assert len(resp.json()["items"]) == 1

    # Beyond last page
    resp = client.get(f"/transcriptions?poi_id={poi_id}&page=10&page_size=2", headers=HEADERS)
    assert resp.json()["items"] == []


def test_list_transcriptions_page_size_max(client):
    resp = client.get("/transcriptions?page_size=101", headers=HEADERS)
    assert resp.status_code == 422


def test_list_transcriptions_page_zero_rejected(client):
    resp = client.get("/transcriptions?page=0", headers=HEADERS)
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════════════


def test_auth_required_list(client):
    resp = client.get("/transcriptions")
    assert resp.status_code == 401


def test_auth_required_start(client):
    resp = client.post(f"/transcriptions/start?poi_id={uuid.uuid4()}&asset_video_id={uuid.uuid4()}")
    assert resp.status_code == 401


def test_auth_wrong_key(client):
    resp = client.get("/transcriptions", headers={"X-API-Key": "wrong"})
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

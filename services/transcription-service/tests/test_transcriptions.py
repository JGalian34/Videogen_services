"""Tests: Transcription start + get."""

import uuid
from tests.conftest import HEADERS


def test_start_transcription(client):
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    resp = client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"  # Stub completes immediately
    assert data["text"] is not None
    assert data["confidence"] == 0.95
    assert len(data["segments"]) == 3


def test_list_transcriptions(client):
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )

    resp = client.get(f"/transcriptions?poi_id={poi_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_transcription(client):
    poi_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())

    resp = client.post(
        f"/transcriptions/start?poi_id={poi_id}&asset_video_id={asset_id}",
        headers=HEADERS,
    )
    tid = resp.json()["id"]

    resp = client.get(f"/transcriptions/{tid}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200


# ── Error tests ────────────────────────────────────────────────────


def test_get_transcription_not_found(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/transcriptions/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_missing_api_key(client):
    resp = client.get("/transcriptions")
    assert resp.status_code == 401


def test_start_transcription_missing_params(client):
    resp = client.post("/transcriptions/start", headers=HEADERS)
    assert resp.status_code == 422

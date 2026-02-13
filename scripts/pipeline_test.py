#!/usr/bin/env python3
"""
Full business pipeline test with mock data.

Exercises the complete flow:
  1. Create POI           (poi-service)
  2. Validate + Publish   (poi-service)
  3. Upload assets        (asset-service)
  4. Generate script      (script-service → fetches POI + assets via HTTP)
  5. Generate voiceover   (transcription-service → ElevenLabs stub TTS)
  6. Poll render job      (render-service → created from script.generated Kafka event)
  7. Attach voiceover     (render-service)
  8. Publish video        (render-service → generates delivery URL)
  9. Final validation     (verify all states are coherent)

Usage:
  python scripts/pipeline_test.py
  python scripts/pipeline_test.py --base-url http://localhost  # custom base
  API_KEY=my-key python scripts/pipeline_test.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import httpx

# ── Configuration ────────────────────────────────────────────────

API_KEY = os.getenv("API_KEY", "dev-api-key")
BASE = os.getenv("BASE_URL", "http://localhost")

POI_URL = os.getenv("POI_BASE_URL", f"{BASE}:8001")
ASSET_URL = os.getenv("ASSET_BASE_URL", f"{BASE}:8002")
SCRIPT_URL = os.getenv("SCRIPT_BASE_URL", f"{BASE}:8003")
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_BASE_URL", f"{BASE}:8004")
RENDER_URL = os.getenv("RENDER_BASE_URL", f"{BASE}:8005")

TIMEOUT = 15.0
POLL_MAX = 90  # seconds
POLL_INTERVAL = 2  # seconds


def headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Correlation-Id": str(uuid.uuid4()),
    }


def step(name: str):
    """Print a step header."""
    print(f"\n{'─' * 60}")
    print(f"  STEP: {name}")
    print(f"{'─' * 60}")


def ok(msg: str, data: dict | None = None):
    print(f"  ✅ {msg}")
    if data:
        print(f"     → {json.dumps(data, indent=2, default=str)[:500]}")


def fail(msg: str):
    print(f"  ❌ {msg}")
    sys.exit(1)


def assert_status(resp: httpx.Response, expected: int, label: str):
    if resp.status_code != expected:
        fail(f"{label}: expected {expected}, got {resp.status_code} – {resp.text[:300]}")


def poll(client: httpx.Client, url: str, check_fn, label: str = "poll"):
    """Poll URL until check_fn(resp) is True."""
    deadline = time.monotonic() + POLL_MAX
    backoff = POLL_INTERVAL
    while time.monotonic() < deadline:
        resp = client.get(url, headers=headers(), timeout=TIMEOUT)
        if check_fn(resp):
            return resp
        time.sleep(backoff)
        backoff = min(backoff * 1.3, 8)
    fail(f"{label}: timed out after {POLL_MAX}s")


# ── Pipeline ─────────────────────────────────────────────────────

def run_pipeline():
    print("\n" + "═" * 60)
    print("  🏠 FULL BUSINESS PIPELINE TEST")
    print("  POI → Assets → Script → Voiceover → Render → Publish")
    print("═" * 60)

    t0 = time.monotonic()

    with httpx.Client(timeout=TIMEOUT) as c:

        # ── 1. Create POI ─────────────────────────────────────
        step("1. Create POI")
        resp = c.post(f"{POI_URL}/pois", headers=headers(), json={
            "name": "Villa Méditerranée – Pipeline Test",
            "description": (
                "Magnifique villa de 250m² avec vue mer, piscine à débordement, "
                "5 chambres, jardin paysager de 1200m², quartier résidentiel calme. "
                "Finitions haut de gamme, cuisine équipée Bulthaup, sol en marbre de Carrare."
            ),
            "address": "42 Avenue de la Corniche, 13007 Marseille",
            "lat": 43.2695,
            "lon": 5.3698,
            "poi_type": "villa",
            "tags": ["mer", "piscine", "luxe", "5-chambres", "marseille"],
        })
        assert_status(resp, 201, "create POI")
        poi = resp.json()
        poi_id = poi["id"]
        assert poi["status"] == "draft", f"Expected draft, got {poi['status']}"
        ok(f"POI created: {poi_id}", {"name": poi["name"], "status": poi["status"]})

        # ── 2. Validate + Publish ─────────────────────────────
        step("2. Validate POI")
        resp = c.post(f"{POI_URL}/pois/{poi_id}/validate", headers=headers())
        assert_status(resp, 200, "validate")
        assert resp.json()["status"] == "validated"
        ok("POI validated")

        step("3. Publish POI")
        resp = c.post(f"{POI_URL}/pois/{poi_id}/publish", headers=headers())
        assert_status(resp, 200, "publish")
        assert resp.json()["status"] == "published"
        ok("POI published", {"version": resp.json().get("version")})

        # ── 3. Create Assets ──────────────────────────────────
        step("4. Create Assets (photo + video)")
        assets = []
        for asset_data in [
            {
                "poi_id": poi_id,
                "name": "villa_facade_4k.jpg",
                "asset_type": "photo",
                "description": "Photo façade haute résolution – drone DJI Mavic 3",
                "file_path": "/data/assets/villa_facade_4k.jpg",
                "mime_type": "image/jpeg",
                "file_size": 8_500_000,
            },
            {
                "poi_id": poi_id,
                "name": "villa_interieur_panoramic.jpg",
                "asset_type": "photo",
                "description": "Panoramique intérieur 360° – salon + cuisine",
                "file_path": "/data/assets/villa_interieur_panoramic.jpg",
                "mime_type": "image/jpeg",
                "file_size": 12_300_000,
            },
            {
                "poi_id": poi_id,
                "name": "visite_virtuelle_brute.mp4",
                "asset_type": "video",
                "description": "Vidéo brute visite complète – 4K 60fps – 3min42",
                "file_path": "/data/assets/visite_virtuelle_brute.mp4",
                "mime_type": "video/mp4",
                "file_size": 524_288_000,
            },
        ]:
            resp = c.post(f"{ASSET_URL}/assets", headers=headers(), json=asset_data)
            assert_status(resp, 201, f"create asset {asset_data['name']}")
            assets.append(resp.json())
            ok(f"Asset: {asset_data['name']} ({asset_data['asset_type']})")

        # Verify listing
        resp = c.get(f"{ASSET_URL}/assets", params={"poi_id": poi_id}, headers=headers())
        assert_status(resp, 200, "list assets")
        assert len(resp.json()["items"]) == 3, f"Expected 3 assets, got {len(resp.json()['items'])}"
        ok(f"Assets verified: {len(resp.json()['items'])} linked to POI")

        # ── 4. Generate Video Script ──────────────────────────
        step("5. Generate Video Script (multi-scene)")
        resp = c.post(f"{SCRIPT_URL}/scripts/generate", params={"poi_id": poi_id}, headers=headers())
        assert_status(resp, 201, "generate script")
        script = resp.json()
        script_id = script["id"]
        scenes = script.get("scenes", [])
        narration = script.get("narration_text", "")
        ok(f"Script generated: {script_id}", {
            "title": script["title"],
            "scenes": len(scenes),
            "duration": script["total_duration_seconds"],
            "narration_preview": narration[:100] + "..." if len(narration) > 100 else narration,
        })
        assert len(scenes) > 0, "Script must have at least 1 scene"
        assert narration, "Script must have narration text"

        # ── 5. Generate Voiceover (ElevenLabs TTS) ───────────
        step("6. Generate Voiceover (ElevenLabs TTS – stub)")
        resp = c.post(f"{TRANSCRIPTION_URL}/voiceovers/generate", headers=headers(), json={
            "poi_id": poi_id,
            "script_id": script_id,
            "narration_text": narration,
            "scenes": scenes,
            "language": "fr",
        })
        assert_status(resp, 201, "generate voiceover")
        voiceover = resp.json()
        voiceover_id = voiceover["id"]
        ok(f"Voiceover generated: {voiceover_id}", {
            "status": voiceover["status"],
            "provider": voiceover["provider"],
            "duration": voiceover.get("total_duration_seconds"),
            "audio": voiceover.get("full_audio_path"),
            "scene_audios_count": len(voiceover.get("scene_audios") or []),
        })
        assert voiceover["status"] == "completed", f"Voiceover should be completed, got {voiceover['status']}"
        assert voiceover.get("full_audio_path"), "Voiceover must have audio path"

        # ── 6. Poll for Render Job ────────────────────────────
        step("7. Wait for Render Job (Kafka: script.generated → render-service)")
        print("     Polling render-service for job created from Kafka event...")

        resp = poll(
            c,
            f"{RENDER_URL}/renders?poi_id={poi_id}",
            lambda r: r.status_code == 200 and len(r.json().get("items", [])) > 0,
            label="render job creation",
        )
        renders = resp.json()["items"]
        render_id = renders[0]["id"]
        render_status = renders[0]["status"]
        render_scenes = renders[0].get("scenes", [])
        ok(f"Render job found: {render_id}", {
            "status": render_status,
            "total_scenes": renders[0].get("total_scenes"),
            "completed_scenes": renders[0].get("completed_scenes"),
            "scenes_rendered": len(render_scenes),
        })

        # Poll until completed (stub is fast)
        if render_status != "completed":
            print("     Waiting for render completion...")
            resp = poll(
                c,
                f"{RENDER_URL}/renders/{render_id}",
                lambda r: r.status_code == 200 and r.json().get("status") == "completed",
                label="render completion",
            )
            ok("Render completed")
        else:
            ok(f"Render already completed with {len(render_scenes)} scenes")

        # ── 7. Attach Voiceover to Render ─────────────────────
        step("8. Attach Voiceover to Render")
        resp = c.post(f"{RENDER_URL}/renders/{render_id}/voiceover", headers=headers(), json={
            "voiceover_id": str(voiceover_id),
            "audio_path": voiceover["full_audio_path"],
        })
        assert_status(resp, 200, "attach voiceover")
        render_data = resp.json()
        ok("Voiceover attached to render", {
            "voiceover_audio_path": render_data.get("voiceover_audio_path"),
            "voiceover_id": render_data.get("voiceover_id"),
        })

        # ── 8. Publish Video Online ───────────────────────────
        step("9. Publish Video (generate delivery URL)")
        resp = c.post(f"{RENDER_URL}/renders/{render_id}/publish", headers=headers())
        assert_status(resp, 200, "publish video")
        published = resp.json()
        ok(f"Video published!", {
            "published_url": published.get("published_url"),
            "published_at": published.get("published_at"),
            "output_path": published.get("output_path"),
            "voiceover_audio": published.get("voiceover_audio_path"),
        })
        assert published.get("published_url"), "Published URL must exist"

        # ── 9. Final Consistency Check ────────────────────────
        step("10. Final Consistency Check")

        # POI still published
        resp = c.get(f"{POI_URL}/pois/{poi_id}", headers=headers())
        assert_status(resp, 200, "get POI")
        assert resp.json()["status"] == "published"
        ok("POI still published ✓")

        # Assets intact
        resp = c.get(f"{ASSET_URL}/assets", params={"poi_id": poi_id}, headers=headers())
        assert resp.json()["total"] == 3
        ok("3 assets intact ✓")

        # Script intact
        resp = c.get(f"{SCRIPT_URL}/scripts/{script_id}", headers=headers())
        assert_status(resp, 200, "get script")
        ok("Script intact ✓")

        # Voiceover intact
        resp = c.get(f"{TRANSCRIPTION_URL}/voiceovers/{voiceover_id}", headers=headers())
        assert_status(resp, 200, "get voiceover")
        assert resp.json()["status"] == "completed"
        ok("Voiceover intact (completed) ✓")

        # Render published
        resp = c.get(f"{RENDER_URL}/renders/{render_id}", headers=headers())
        assert_status(resp, 200, "get render")
        render_final = resp.json()
        assert render_final["status"] == "completed"
        assert render_final.get("published_url"), "Published URL must exist"
        ok("Render published with delivery URL ✓")

    elapsed = time.monotonic() - t0

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  🎉 PIPELINE COMPLETE – ALL CHECKS PASSED")
    print("═" * 60)
    print(f"""
  Pipeline Summary:
  ─────────────────────────────────────────
  POI:          {poi_id}
  Assets:       3 (2 photos + 1 video)
  Script:       {script_id} ({len(scenes)} scenes, {script.get('total_duration_seconds', 0)}s)
  Voiceover:    {voiceover_id} ({voiceover.get('provider')}, {voiceover.get('total_duration_seconds', 0):.1f}s)
  Render:       {render_id} ({len(render_scenes)} scenes rendered)
  Published:    {published.get('published_url')}
  Duration:     {elapsed:.1f}s
  ─────────────────────────────────────────

  Business Flow:
    POI Data ──────────┐
    Assets ────────────┤
                       ▼
    Script Service ────── script.generated ──┐
         │                                   │
         ├── narration_text                  ▼
         │                           Render Service
         ▼                           (Runway stub)
    Voiceover Service                    │
    (ElevenLabs stub)                    │
         │                               │
         └──── attach voiceover ─────────┤
                                         ▼
                                   Publish Video
                                   (CDN delivery URL)
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full pipeline test")
    parser.add_argument("--base-url", default=None, help="Base URL override")
    args = parser.parse_args()
    if args.base_url:
        BASE = args.base_url

    run_pipeline()


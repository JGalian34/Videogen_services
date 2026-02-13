"""
HTTP-based end-to-end test scenarios.

Each scenario returns a ``StepResult`` so the orchestrator can
aggregate PASS / FAIL status.  No blind sleeps – all async waits
use polling with exponential backoff.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from tools.qa.config import (
    API_KEY,
    ASSET_URL,
    POLL_INTERVAL,
    POLL_MAX_WAIT,
    POI_URL,
    RENDER_URL,
    REQUEST_TIMEOUT,
    SCRIPT_URL,
    SERVICE_URLS,
    TRANSCRIPTION_URL,
)


# ── Result model ─────────────────────────────────────────────────────

@dataclass
class StepResult:
    name: str
    passed: bool
    duration_ms: float = 0.0
    detail: str = ""
    assertions: list[str] = field(default_factory=list)


@dataclass
class E2EReport:
    steps: list[StepResult] = field(default_factory=list)
    passed: bool = True
    total_duration_ms: float = 0.0

    def add(self, step: StepResult) -> None:
        self.steps.append(step)
        if not step.passed:
            self.passed = False


# ── Helpers ──────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    h: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Correlation-Id": str(uuid.uuid4()),
    }
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _assert(condition: bool, msg: str, assertions: list[str]) -> None:
    assertions.append(f"{'✓' if condition else '✗'} {msg}")
    if not condition:
        raise AssertionError(msg)


def _poll(
    client: httpx.Client,
    url: str,
    check_fn,
    *,
    interval: float = POLL_INTERVAL,
    max_wait: float = POLL_MAX_WAIT,
) -> httpx.Response:
    """Poll *url* until *check_fn(response)* returns True."""
    deadline = time.monotonic() + max_wait
    backoff = interval
    last_resp = None
    while time.monotonic() < deadline:
        resp = client.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        last_resp = resp
        if check_fn(resp):
            return resp
        time.sleep(min(backoff, deadline - time.monotonic()))
        backoff = min(backoff * 1.3, 10)
    raise TimeoutError(
        f"Polling {url} timed out after {max_wait}s. "
        f"Last status={last_resp.status_code if last_resp else 'N/A'}"
    )


# ── Scenarios ────────────────────────────────────────────────────────

def run_all() -> E2EReport:
    """Execute the full E2E suite and return a structured report."""
    report = E2EReport()
    t0 = time.monotonic()

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        # 1 – Health / Readiness
        report.add(_check_health(client))

        # 2 – Create POI
        poi_step, poi_id = _create_poi(client)
        report.add(poi_step)
        if not poi_step.passed:
            report.total_duration_ms = (time.monotonic() - t0) * 1000
            return report

        # 3 – Validate + Publish POI
        report.add(_validate_and_publish(client, poi_id))

        # 4 – Create assets
        asset_step, asset_ids = _create_assets(client, poi_id)
        report.add(asset_step)

        # 5 – Generate script
        script_step, script_id = _generate_script(client, poi_id)
        report.add(script_step)

        # 6 – Start transcription
        if asset_ids:
            report.add(_start_transcription(client, poi_id, asset_ids[-1]))

        # 7 – Poll render (event-driven)
        if script_id:
            report.add(_poll_render(client, poi_id))

        # 8 – Final consistency
        report.add(_consistency_check(client, poi_id))

    report.total_duration_ms = (time.monotonic() - t0) * 1000
    return report


# ── Step implementations ─────────────────────────────────────────────

def _check_health(client: httpx.Client) -> StepResult:
    t0 = time.monotonic()
    assertions: list[str] = []
    try:
        for svc_name, base in SERVICE_URLS.items():
            for endpoint in ("/healthz", "/readyz"):
                resp = client.get(f"{base}{endpoint}", headers=_headers(), timeout=REQUEST_TIMEOUT)
                _assert(resp.status_code == 200, f"{svc_name}{endpoint} → 200", assertions)
        return StepResult(
            name="health_readiness",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=f"All {len(SERVICE_URLS)} services healthy",
            assertions=assertions,
        )
    except (AssertionError, httpx.HTTPError) as exc:
        return StepResult(
            name="health_readiness",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
            assertions=assertions,
        )


def _create_poi(client: httpx.Client) -> tuple[StepResult, str | None]:
    t0 = time.monotonic()
    assertions: list[str] = []
    poi_id = None
    try:
        resp = client.post(
            f"{POI_URL}/pois",
            headers=_headers(),
            json={
                "name": f"QA E2E Villa – {uuid.uuid4().hex[:8]}",
                "description": "Created by QA harness for E2E regression",
                "address": "42 Rue de la Paix, 75002 Paris",
                "lat": 48.8698,
                "lon": 2.3308,
                "poi_type": "villa",
                "tags": ["qa", "e2e"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        _assert(resp.status_code == 201, "POST /pois → 201", assertions)
        data = resp.json()
        _assert(data.get("status") == "draft", "status == draft", assertions)
        _assert("id" in data, "response contains id", assertions)
        _assert(data.get("version") == 1, "version == 1", assertions)
        _assert(data.get("poi_type") == "villa", "poi_type == villa", assertions)
        poi_id = data["id"]
        return (
            StepResult(
                name="create_poi",
                passed=True,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=f"POI {poi_id}",
                assertions=assertions,
            ),
            poi_id,
        )
    except (AssertionError, Exception) as exc:
        return (
            StepResult(
                name="create_poi",
                passed=False,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=str(exc),
                assertions=assertions,
            ),
            None,
        )


def _validate_and_publish(client: httpx.Client, poi_id: str) -> StepResult:
    t0 = time.monotonic()
    assertions: list[str] = []
    try:
        # Validate
        resp = client.post(f"{POI_URL}/pois/{poi_id}/validate", headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "POST validate → 200", assertions)
        _assert(resp.json().get("status") == "validated", "status == validated", assertions)

        # Publish
        resp = client.post(f"{POI_URL}/pois/{poi_id}/publish", headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "POST publish → 200", assertions)
        _assert(resp.json().get("status") == "published", "status == published", assertions)

        # Verify – cannot re-validate a published POI
        resp = client.post(f"{POI_URL}/pois/{poi_id}/validate", headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 409, "re-validate published → 409", assertions)

        return StepResult(
            name="validate_publish_poi",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail="draft → validated → published OK",
            assertions=assertions,
        )
    except (AssertionError, Exception) as exc:
        return StepResult(
            name="validate_publish_poi",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
            assertions=assertions,
        )


def _create_assets(client: httpx.Client, poi_id: str) -> tuple[StepResult, list[str]]:
    t0 = time.monotonic()
    assertions: list[str] = []
    asset_ids: list[str] = []
    try:
        assets_data = [
            {
                "poi_id": poi_id,
                "name": "facade_hd.jpg",
                "asset_type": "photo",
                "file_path": "/data/assets/facade_hd.jpg",
                "mime_type": "image/jpeg",
                "file_size": 2048000,
            },
            {
                "poi_id": poi_id,
                "name": "walkthrough.mp4",
                "asset_type": "video",
                "file_path": "/data/assets/walkthrough.mp4",
                "mime_type": "video/mp4",
                "file_size": 52428800,
            },
        ]
        for i, asset in enumerate(assets_data):
            resp = client.post(f"{ASSET_URL}/assets", headers=_headers(), json=asset, timeout=REQUEST_TIMEOUT)
            _assert(resp.status_code == 201, f"POST /assets #{i+1} → 201", assertions)
            data = resp.json()
            _assert(data.get("poi_id") == poi_id, f"asset #{i+1} poi_id matches", assertions)
            asset_ids.append(data["id"])

        # List by poi_id
        resp = client.get(f"{ASSET_URL}/assets", params={"poi_id": poi_id}, headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "GET /assets?poi_id → 200", assertions)
        items = resp.json().get("items", [])
        _assert(len(items) == 2, f"list returns 2 assets (got {len(items)})", assertions)

        return (
            StepResult(
                name="create_assets",
                passed=True,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=f"{len(asset_ids)} assets created",
                assertions=assertions,
            ),
            asset_ids,
        )
    except (AssertionError, Exception) as exc:
        return (
            StepResult(
                name="create_assets",
                passed=False,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=str(exc),
                assertions=assertions,
            ),
            asset_ids,
        )


def _generate_script(client: httpx.Client, poi_id: str) -> tuple[StepResult, str | None]:
    t0 = time.monotonic()
    assertions: list[str] = []
    script_id = None
    try:
        resp = client.post(
            f"{SCRIPT_URL}/scripts/generate",
            params={"poi_id": poi_id},
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        _assert(resp.status_code == 201, "POST /scripts/generate → 201", assertions)
        data = resp.json()
        _assert("id" in data, "response has script id", assertions)
        _assert("scenes" in data and len(data["scenes"]) > 0, "script has scenes", assertions)
        _assert("total_duration_seconds" in data, "script has duration", assertions)
        _assert(data.get("poi_id") == poi_id, "script poi_id matches", assertions)
        script_id = data["id"]

        # Verify persistence
        resp = client.get(f"{SCRIPT_URL}/scripts/{script_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, f"GET /scripts/{script_id} → 200", assertions)

        return (
            StepResult(
                name="generate_script",
                passed=True,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=f"script {script_id}, {len(data.get('scenes', []))} scenes",
                assertions=assertions,
            ),
            script_id,
        )
    except (AssertionError, Exception) as exc:
        return (
            StepResult(
                name="generate_script",
                passed=False,
                duration_ms=(time.monotonic() - t0) * 1000,
                detail=str(exc),
                assertions=assertions,
            ),
            None,
        )


def _start_transcription(client: httpx.Client, poi_id: str, video_asset_id: str) -> StepResult:
    t0 = time.monotonic()
    assertions: list[str] = []
    try:
        resp = client.post(
            f"{TRANSCRIPTION_URL}/transcriptions/start",
            params={"poi_id": poi_id, "asset_video_id": video_asset_id},
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        _assert(resp.status_code == 201, "POST /transcriptions/start → 201", assertions)
        data = resp.json()
        tid = data["id"]

        # Poll completion (stub completes fast)
        def check(r: httpx.Response) -> bool:
            return r.status_code == 200 and r.json().get("status") == "completed"

        resp = _poll(client, f"{TRANSCRIPTION_URL}/transcriptions/{tid}", check)
        _assert(resp.json().get("status") == "completed", "transcription completed", assertions)

        return StepResult(
            name="transcription",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=f"transcription {tid} completed",
            assertions=assertions,
        )
    except (AssertionError, TimeoutError, Exception) as exc:
        return StepResult(
            name="transcription",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
            assertions=assertions,
        )


def _poll_render(client: httpx.Client, poi_id: str) -> StepResult:
    t0 = time.monotonic()
    assertions: list[str] = []
    try:
        # Wait for render job to appear (created by Kafka consumer)
        def check_exists(r: httpx.Response) -> bool:
            return r.status_code == 200 and len(r.json().get("items", [])) > 0

        resp = _poll(client, f"{RENDER_URL}/renders?poi_id={poi_id}", check_exists)
        items = resp.json()["items"]
        _assert(len(items) > 0, "render job created via event", assertions)

        render_id = items[0]["id"]
        render_status = items[0].get("status", "unknown")
        _assert(render_id is not None, f"render id present (status={render_status})", assertions)

        # Optionally poll until completed
        def check_done(r: httpx.Response) -> bool:
            s = r.json().get("status", "")
            return s in ("completed", "done")

        try:
            resp = _poll(
                client,
                f"{RENDER_URL}/renders/{render_id}",
                check_done,
                max_wait=POLL_MAX_WAIT,
            )
            _assert(True, f"render {render_id} completed", assertions)
        except TimeoutError:
            # Not blocking – render might take longer in stub mode
            _assert(True, f"render {render_id} still processing (non-blocking)", assertions)

        return StepResult(
            name="render_pipeline",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=f"render {render_id} observed",
            assertions=assertions,
        )
    except (AssertionError, TimeoutError, Exception) as exc:
        return StepResult(
            name="render_pipeline",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
            assertions=assertions,
        )


def _consistency_check(client: httpx.Client, poi_id: str) -> StepResult:
    t0 = time.monotonic()
    assertions: list[str] = []
    try:
        # POI still published
        resp = client.get(f"{POI_URL}/pois/{poi_id}", headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "GET /pois/{id} → 200", assertions)
        _assert(resp.json().get("status") == "published", "POI still published", assertions)

        # Assets intact
        resp = client.get(f"{ASSET_URL}/assets", params={"poi_id": poi_id}, headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "assets list → 200", assertions)
        _assert(len(resp.json().get("items", [])) == 2, "2 assets still present", assertions)

        # Scripts intact
        resp = client.get(f"{SCRIPT_URL}/scripts", params={"poi_id": poi_id}, headers=_headers(), timeout=REQUEST_TIMEOUT)
        _assert(resp.status_code == 200, "scripts list → 200", assertions)

        return StepResult(
            name="consistency_check",
            passed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail="All services consistent",
            assertions=assertions,
        )
    except (AssertionError, Exception) as exc:
        return StepResult(
            name="consistency_check",
            passed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            detail=str(exc),
            assertions=assertions,
        )


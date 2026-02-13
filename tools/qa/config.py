"""
Centralised QA configuration.

Every value is overridable via environment variables so CI and local
invocations share the same harness with different knobs.

Hierarchy:  env var → default here.
"""

from __future__ import annotations

import os

# ── Service URLs ─────────────────────────────────────────────────────
POI_URL = os.getenv("POI_BASE_URL", "http://localhost:8001")
ASSET_URL = os.getenv("ASSET_BASE_URL", "http://localhost:8002")
SCRIPT_URL = os.getenv("SCRIPT_BASE_URL", "http://localhost:8003")
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_BASE_URL", "http://localhost:8004")
RENDER_URL = os.getenv("RENDER_BASE_URL", "http://localhost:8005")

SERVICE_URLS: dict[str, str] = {
    "poi-service": POI_URL,
    "asset-service": ASSET_URL,
    "script-service": SCRIPT_URL,
    "transcription-service": TRANSCRIPTION_URL,
    "render-service": RENDER_URL,
}

API_KEY = os.getenv("API_KEY", "dev-api-key")

# ── HTTP settings ────────────────────────────────────────────────────
REQUEST_TIMEOUT = float(os.getenv("QA_REQUEST_TIMEOUT", "15"))
POLL_INTERVAL = float(os.getenv("QA_POLL_INTERVAL", "2"))
POLL_MAX_WAIT = float(os.getenv("QA_POLL_MAX_WAIT", "120"))

# ── SLO thresholds (configurable) ───────────────────────────────────
SLO_ERROR_RATE_PCT = float(os.getenv("SLO_ERROR_RATE_PCT", "1.0"))
SLO_READ_P95_MS = float(os.getenv("SLO_READ_P95_MS", "500"))
SLO_WRITE_P95_MS = float(os.getenv("SLO_WRITE_P95_MS", "1500"))
SLO_MAX_RESTARTS = int(os.getenv("SLO_MAX_RESTARTS", "0"))

# ── Load test parameters ─────────────────────────────────────────────
LOAD_VUS_BASELINE = int(os.getenv("LOAD_VUS_BASELINE", "10"))
LOAD_VUS_HIGH = int(os.getenv("LOAD_VUS_HIGH", "200"))
LOAD_VUS_SPIKE = int(os.getenv("LOAD_VUS_SPIKE", "1000"))
LOAD_VUS_SOAK = int(os.getenv("LOAD_VUS_SOAK", "100"))
LOAD_DURATION_BASELINE = os.getenv("LOAD_DURATION_BASELINE", "1m")
LOAD_DURATION_HIGH = os.getenv("LOAD_DURATION_HIGH", "3m")
LOAD_DURATION_SOAK = os.getenv("LOAD_DURATION_SOAK", "10m")

# ── Docker stats sampling ────────────────────────────────────────────
DOCKER_STATS_ENABLED = os.getenv("QA_DOCKER_STATS", "1").lower() in ("1", "true", "yes")
DOCKER_STATS_INTERVAL_S = float(os.getenv("QA_DOCKER_STATS_INTERVAL", "5"))
DOCKER_STATS_SAMPLES = int(os.getenv("QA_DOCKER_STATS_SAMPLES", "6"))

# ── Coverage ─────────────────────────────────────────────────────────
COVERAGE_ENABLED = os.getenv("QA_COVERAGE", "0").lower() in ("1", "true", "yes")

# ── Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts", "qa")
K6_SCRIPT = os.path.join(os.path.dirname(__file__), "load", "k6", "load.js")

# ── Docker ───────────────────────────────────────────────────────────
COMPOSE_FILE = os.path.join(PROJECT_ROOT, "docker-compose.yml")

SERVICES = [
    "poi-service",
    "asset-service",
    "script-service",
    "transcription-service",
    "render-service",
]

SERVICE_PORTS: dict[str, int] = {
    "poi-service": 8001,
    "asset-service": 8002,
    "script-service": 8003,
    "transcription-service": 8004,
    "render-service": 8005,
}

# ── Unit test environment (shared across all services) ───────────────
UNIT_TEST_ENV: dict[str, str] = {
    "POSTGRES_HOST": "",
    "POSTGRES_DB": "",
    "API_KEY": "test-key",
    "LOG_FORMAT": "text",
    "RUNWAY_MODE": "stub",
    "NLP_PROVIDER": "stub",
    "ELEVENLABS_MODE": "stub",
}

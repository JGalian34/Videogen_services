# QA Harness – Real Estate POI Video Platform

Single-command quality pipeline covering lint, unit tests, E2E HTTP
scenarios, and high-load stress testing with clear PASS/FAIL reporting.

## Quick Start

```bash
# Full pipeline (docker-compose up → lint → test → E2E → load → report → down)
make qa

# Fast (lint + unit only, no Docker)
make qa-fast

# E2E only (services must already be running)
make qa-e2e

# Load test only (services must already be running, requires k6)
make qa-load

# Full pipeline with coverage
make qa-coverage

# Cleanup (compose down -v + remove artifacts)
make qa-clean
```

## Architecture

```
tools/qa/
├── run.py           # Orchestrator – drives all phases
├── config.py        # URLs, API key, SLO thresholds (env-overridable)
├── http_e2e.py      # E2E HTTP test scenarios
├── report.py        # Report generator (JSON + Markdown + console)
├── requirements.txt # Python deps for the harness
├── README.md        # This file
└── load/
    └── k6/
        └── load.js  # k6 load test (4 scenarios)
```

## Pipeline Phases

| Phase | Tool | What it does |
|-------|------|--------------|
| 1. Compose up | docker compose | Starts all infra + services |
| 2. Readiness | polling /readyz | Waits for all 5 services (exponential backoff) |
| 3. Lint | ruff + black + mypy | Checks all services |
| 4. Unit tests | pytest | Per-service, JUnit XML + optional coverage |
| 5. E2E HTTP | httpx (Python) | Full business workflow + error paths |
| 6. Load test | k6 | 4 scenarios (baseline/high/spike/soak) |
| 7. Docker stats | docker stats | Container CPU/mem sampling + restart count |
| 8. Report | Python | JSON + Markdown + console table |

## E2E Scenario

1. Health/readiness → all 5 services
2. Create POI (draft) → update fields + verify version bump → validate → publish
3. Create 2 assets linked to POI
4. Generate video script via script-service
5. Start transcription (stub pipeline)
6. Poll render job (created via Kafka event)
7. Consistency check (POI still published, assets intact)
8. Archive POI → verify final status
9. Error path: create POI with invalid data → verify 422

## Load Test Scenarios (k6)

| Scenario | VUs | Duration | Mix |
|----------|-----|----------|-----|
| baseline | 10 | 1 min | 80% read / 20% write |
| high_load | 200 (configurable) | 3 min + ramp | 90% read / 10% write |
| spike | 1000 VUs burst over 30s | ~50s | 90% read / 10% write |
| soak | 100 | 10 min | 80% read / 20% write |

Load endpoints tested:
- `GET /pois` (list with pagination)
- `POST /pois` (create)
- `PATCH /pois/{id}` (update)
- `GET /assets?poi_id=` (assets list)
- `POST /scripts/generate` (script generation)

Run a single scenario:
```bash
k6 run tools/qa/load/k6/load.js --env SCENARIO=baseline
```

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `POI_BASE_URL` | http://localhost:8001 | POI service URL |
| `ASSET_BASE_URL` | http://localhost:8002 | Asset service URL |
| `SCRIPT_BASE_URL` | http://localhost:8003 | Script service URL |
| `TRANSCRIPTION_BASE_URL` | http://localhost:8004 | Transcription service URL |
| `RENDER_BASE_URL` | http://localhost:8005 | Render service URL |
| `API_KEY` | dev-api-key | API authentication key |
| `SLO_ERROR_RATE_PCT` | 1.0 | Max error rate % |
| `SLO_READ_P95_MS` | 500 | Max read p95 latency (ms) |
| `SLO_WRITE_P95_MS` | 1500 | Max write p95 latency (ms) |
| `SLO_MAX_RESTARTS` | 0 | Max container restarts |
| `LOAD_VUS_HIGH` | 200 | VUs for high-load scenario |
| `LOAD_VUS_SPIKE` | 1000 | VUs for spike scenario |
| `LOAD_VUS_SOAK` | 100 | VUs for soak scenario |
| `QA_DOCKER_STATS` | 0 | Enable CPU/mem sampling via docker stats |
| `QA_COVERAGE` | 0 | Enable pytest coverage collection |

## Artifacts

After `make qa`, find in `artifacts/qa/`:

| File | Format | Content |
|------|--------|---------|
| `report.json` | JSON | Machine-readable full report |
| `report.md` | Markdown | Human-readable report with recommendations |
| `k6-summary.json` | JSON | k6 metrics summary |
| `junit-<service>.xml` | JUnit XML | Per-service test results |
| `coverage-<service>.xml` | Cobertura XML | Per-service coverage (if enabled) |

## Robustness Features

The following resilience patterns are validated by the QA harness:

- **Connection pooling**: All services use SQLAlchemy engine with `pool_size=10`, `max_overflow=20`, `pool_recycle=300s`, `pool_pre_ping=True`
- **HTTP client pooling**: `ServiceClient` reuses `httpx.AsyncClient` instances across requests
- **Kafka idempotence**: Render-service consumer deduplicates events by `event_id`
- **Request size limits**: `RequestSizeLimitMiddleware` on all services
- **API key auth**: `APIKeyMiddleware` protects all endpoints
- **Timeouts**: Configurable HTTP timeouts on all inter-service clients
- **Pagination**: All list endpoints enforce `limit`/`offset` pagination

## Example Report Output

```
══════════════════════════════════════════════════════════════
  QA REPORT
══════════════════════════════════════════════════════════════
  ✅ readiness                     1823ms  All 5 services ready
  ✅ lint                          4521ms  ruff + black + mypy OK
  ✅ unit_tests                    8934ms  5/5 services passed
  ✅ e2e_http                     12456ms  10/10 steps passed
  ✅ load_test                   185302ms  k6 passed all thresholds

  Load: 45,230 reqs, 251.3 rps, err=0.12%, read_p95=89ms, write_p95=342ms

  Top 5 Slowest (p95):
    1. POST /pois         342ms
    2. POST /scripts      289ms
    3. PATCH /pois/{id}   201ms
    4. GET /assets        112ms
    5. GET /pois           89ms

  Recommendations:
    ✅ All checks passed. System is within SLO bounds.

  ✅ OVERALL PASS  (duration: 213.0s)
══════════════════════════════════════════════════════════════
```

## CI Integration

The `.github/workflows/qa.yml` workflow runs:
- **On push/PR**: `fast` job (lint + unit + coverage per service, matrix strategy)
- **On push to main**: `fast` → `e2e` (docker-compose + E2E HTTP)
- **Nightly (03:00 UTC)**: `fast` → `e2e` → `load` (baseline k6 in CI)
- **Manual dispatch**: Choose whether to include load tests

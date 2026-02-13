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

# Cleanup
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
| 2. Readiness | polling /readyz | Waits for all 5 services (backoff) |
| 3. Lint | ruff + black + mypy | Checks all services |
| 4. Unit tests | pytest | Per-service, JUnit XML output |
| 5. E2E HTTP | httpx (Python) | Full business workflow |
| 6. Load test | k6 | 4 scenarios (baseline/high/spike/soak) |
| 7. Docker stats | docker compose ps | Container restart count |
| 8. Report | Python | JSON + Markdown + console table |

## E2E Scenario

1. Health/readiness → all 5 services
2. Create POI (draft) → validate → publish
3. Create 2 assets linked to POI
4. Generate video script via script-service
5. Start transcription (stub pipeline)
6. Poll render job (created via Kafka event)
7. Consistency check (POI still published, assets intact)

## Load Test Scenarios (k6)

| Scenario | VUs | Duration | Mix |
|----------|-----|----------|-----|
| baseline | 10 | 1 min | 80% read / 20% write |
| high_load | 200 (configurable) | 3 min + ramp | 90% read / 10% write |
| spike | 500 → burst 30s | ~50s | 90% read / 10% write |
| soak | 100 | 10 min | 80% read / 20% write |

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
| `LOAD_VUS_SPIKE` | 500 | VUs for spike scenario |
| `LOAD_VUS_SOAK` | 100 | VUs for soak scenario |

## Artifacts

After `make qa`, find in `artifacts/qa/`:

| File | Format | Content |
|------|--------|---------|
| `report.json` | JSON | Machine-readable full report |
| `report.md` | Markdown | Human-readable report |
| `k6-summary.json` | JSON | k6 metrics summary |
| `junit-<service>.xml` | JUnit XML | Per-service test results |

## Example Report Output

```
══════════════════════════════════════════════════════════════
  QA REPORT
══════════════════════════════════════════════════════════════
  ✅ readiness                     1823ms  All 5 services ready
  ✅ lint                          4521ms  ruff + black + mypy OK
  ✅ unit_tests                    8934ms  5/5 services passed
  ✅ e2e_http                     12456ms  8/8 steps passed
  ✅ load_test                   185302ms  k6 passed all thresholds

  Load: 45,230 reqs, 251.3 rps, err=0.12%, read_p95=89ms, write_p95=342ms

  Recommendations:
    ✅ All checks passed. System is within SLO bounds.

  ✅ OVERALL PASS  (duration: 213.0s)
══════════════════════════════════════════════════════════════
```

## CI Integration

The `qa.yml` workflow runs:
- **On push/PR**: `fast` job (lint + unit per service)
- **On push to main**: `fast` → `e2e` (docker-compose + E2E HTTP)
- **Nightly (03:00 UTC)**: `fast` → `e2e` → `load` (baseline k6 in CI)


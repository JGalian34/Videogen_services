/**
 * k6 load-test suite for the Real Estate POI Video Platform.
 *
 * Scenarios:
 *   1. baseline   – 10 VUs, 1 min, 80/20 read/write mix
 *   2. high_load  – configurable VUs (200–500), 3–5 min ramp-up
 *   3. spike      – burst to 500–1000 VUs over 30 s, then cool-down
 *   4. soak       – 100 VUs, 10 min, watch for memory leaks
 *
 * Usage:
 *   k6 run load.js                                # all scenarios
 *   k6 run load.js --env SCENARIO=baseline        # single scenario
 *   k6 run load.js --env VUS_HIGH=300 --env DURATION_HIGH=5m
 *
 * All URLs / keys are env-overridable.
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString, uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Configuration ─────────────────────────────────────────────────

const POI_URL            = __ENV.POI_BASE_URL           || 'http://localhost:8001';
const ASSET_URL          = __ENV.ASSET_BASE_URL         || 'http://localhost:8002';
const SCRIPT_URL         = __ENV.SCRIPT_BASE_URL        || 'http://localhost:8003';
const RENDER_URL         = __ENV.RENDER_BASE_URL        || 'http://localhost:8005';
const API_KEY            = __ENV.API_KEY                 || 'dev-api-key';
const VUS_HIGH           = parseInt(__ENV.VUS_HIGH       || '200');
const VUS_SPIKE          = parseInt(__ENV.VUS_SPIKE      || '500');
const VUS_SOAK           = parseInt(__ENV.VUS_SOAK       || '100');
const DURATION_HIGH      = __ENV.DURATION_HIGH           || '3m';
const DURATION_SOAK      = __ENV.DURATION_SOAK           || '10m';
const SELECTED_SCENARIO  = __ENV.SCENARIO                || 'all';

// SLO thresholds
const SLO_READ_P95_MS  = parseInt(__ENV.SLO_READ_P95_MS  || '500');
const SLO_WRITE_P95_MS = parseInt(__ENV.SLO_WRITE_P95_MS || '1500');
const SLO_ERROR_RATE   = parseFloat(__ENV.SLO_ERROR_RATE_PCT || '1') / 100;

// ── Custom metrics ────────────────────────────────────────────────

const readLatency  = new Trend('read_latency', true);
const writeLatency = new Trend('write_latency', true);
const errorRate    = new Rate('error_rate');
const errCount     = new Counter('errors_total');

// ── Thresholds ────────────────────────────────────────────────────

export const options = {
  thresholds: {
    'read_latency':  [`p(95)<${SLO_READ_P95_MS}`],
    'write_latency': [`p(95)<${SLO_WRITE_P95_MS}`],
    'error_rate':    [`rate<${SLO_ERROR_RATE}`],
    'http_req_failed': ['rate<0.01'],
  },
  scenarios: buildScenarios(),
};

function buildScenarios() {
  const all = {
    baseline: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1m',
      exec: 'mixedWorkload',
      tags: { scenario: 'baseline' },
    },
    high_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: VUS_HIGH },
        { duration: DURATION_HIGH, target: VUS_HIGH },
        { duration: '30s', target: 0 },
      ],
      exec: 'readHeavy',
      startTime: '1m30s',
      tags: { scenario: 'high_load' },
    },
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: VUS_SPIKE },
        { duration: '30s', target: VUS_SPIKE },
        { duration: '10s', target: 0 },
      ],
      exec: 'readHeavy',
      startTime: '6m',
      tags: { scenario: 'spike' },
    },
    soak: {
      executor: 'constant-vus',
      vus: VUS_SOAK,
      duration: DURATION_SOAK,
      exec: 'mixedWorkload',
      startTime: '7m',
      tags: { scenario: 'soak' },
    },
  };

  if (SELECTED_SCENARIO !== 'all' && all[SELECTED_SCENARIO]) {
    const s = {};
    s[SELECTED_SCENARIO] = all[SELECTED_SCENARIO];
    s[SELECTED_SCENARIO].startTime = '0s';
    return s;
  }
  return all;
}

// ── Headers ───────────────────────────────────────────────────────

function headers() {
  return {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
    'X-Correlation-Id': uuidv4(),
  };
}

// ── Workload functions ────────────────────────────────────────────

// 80% reads / 20% writes
export function mixedWorkload() {
  if (Math.random() < 0.8) {
    doRead();
  } else {
    doWrite();
  }
  sleep(0.1 + Math.random() * 0.3);
}

// 90% reads / 10% writes
export function readHeavy() {
  if (Math.random() < 0.9) {
    doRead();
  } else {
    doWrite();
  }
  sleep(0.05 + Math.random() * 0.15);
}

// ── Read operations ───────────────────────────────────────────────

function doRead() {
  const ops = [listPois, listAssets, getHealth];
  const op = ops[Math.floor(Math.random() * ops.length)];
  op();
}

function listPois() {
  group('GET /pois', () => {
    const page = Math.floor(Math.random() * 5) + 1;
    const res = http.get(`${POI_URL}/pois?page=${page}&page_size=20`, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    const ok = check(res, {
      'list pois status 200': (r) => r.status === 200,
      'list pois has items': (r) => {
        try { return Array.isArray(JSON.parse(r.body).items); } catch(e) { return false; }
      },
    });
    if (!ok) { errorRate.add(1); errCount.add(1); } else { errorRate.add(0); }
  });
}

function listAssets() {
  group('GET /assets', () => {
    const res = http.get(`${ASSET_URL}/assets`, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    const ok = check(res, { 'list assets status 200': (r) => r.status === 200 });
    if (!ok) { errorRate.add(1); errCount.add(1); } else { errorRate.add(0); }
  });
}

function getHealth() {
  group('GET /healthz', () => {
    const urls = [POI_URL, ASSET_URL, SCRIPT_URL, RENDER_URL];
    const url = urls[Math.floor(Math.random() * urls.length)];
    const res = http.get(`${url}/healthz`, { headers: headers(), timeout: '5s' });
    readLatency.add(res.timings.duration);
    const ok = check(res, { 'health 200': (r) => r.status === 200 });
    if (!ok) { errorRate.add(1); errCount.add(1); } else { errorRate.add(0); }
  });
}

// ── Write operations ──────────────────────────────────────────────

function doWrite() {
  group('POST /pois', () => {
    const payload = JSON.stringify({
      name: `k6-Load-${randomString(8)}`,
      description: 'Load test POI created by k6',
      lat: 48.8 + Math.random() * 0.1,
      lon: 2.3 + Math.random() * 0.1,
      poi_type: Math.random() > 0.5 ? 'villa' : 'apartment',
      tags: ['k6', 'load-test'],
    });

    const res = http.post(`${POI_URL}/pois`, payload, { headers: headers(), timeout: '15s' });
    writeLatency.add(res.timings.duration);
    const ok = check(res, {
      'create poi status 201': (r) => r.status === 201,
      'create poi has id': (r) => {
        try { return !!JSON.parse(r.body).id; } catch(e) { return false; }
      },
    });
    if (!ok) { errorRate.add(1); errCount.add(1); } else { errorRate.add(0); }
  });
}

// ── Summary output ────────────────────────────────────────────────

export function handleSummary(data) {
  const outDir = __ENV.ARTIFACTS_DIR || 'artifacts/qa';
  return {
    'stdout':                    textSummary(data, { indent: '  ', enableColors: true }),
    [`${outDir}/k6-summary.json`]: JSON.stringify(data, null, 2),
  };
}

// Minimal text summary (k6 built-in is fine for stdout)
function textSummary(data, opts) {
  // k6 natively prints a great summary to stdout; we just need the JSON file.
  // Return empty string and let k6 do its default console output.
  return '';
}


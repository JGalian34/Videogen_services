/**
 * k6 load-test suite for the Real Estate POI Video Platform.
 *
 * Enterprise-grade load testing with 4 scenarios:
 *   1. baseline   – 10 VUs, 1 min, 80/20 read/write mix (warmup + smoke)
 *   2. high_load  – 200-500 VUs, 3-5 min ramp-up, 90/10 read/write
 *   3. spike      – burst to 1000 VUs over 30s, sustain, then cool-down
 *   4. soak       – 100 VUs, 10 min, monitor stability + memory/errors
 *
 * Endpoints tested:
 *   READ:  GET /pois (paginated, filtered), GET /assets?poi_id=,
 *          GET /scripts?poi_id=, GET /renders?poi_id=, GET /healthz
 *   WRITE: POST /pois (create), PATCH /pois/{id} (update),
 *          POST /assets (create)
 *
 * Usage:
 *   k6 run load.js                                # all scenarios
 *   k6 run load.js --env SCENARIO=baseline        # single scenario
 *   k6 run load.js --env VUS_HIGH=300 --env DURATION_HIGH=5m
 *
 * All URLs / keys / SLO thresholds are env-overridable.
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString, uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Configuration ─────────────────────────────────────────────────

const POI_URL            = __ENV.POI_BASE_URL           || 'http://localhost:8001';
const ASSET_URL          = __ENV.ASSET_BASE_URL         || 'http://localhost:8002';
const SCRIPT_URL         = __ENV.SCRIPT_BASE_URL        || 'http://localhost:8003';
const TRANSCRIPTION_URL  = __ENV.TRANSCRIPTION_BASE_URL || 'http://localhost:8004';
const RENDER_URL         = __ENV.RENDER_BASE_URL        || 'http://localhost:8005';
const API_KEY            = __ENV.API_KEY                 || 'dev-api-key';
const VUS_HIGH           = parseInt(__ENV.VUS_HIGH       || '200');
const VUS_SPIKE          = parseInt(__ENV.VUS_SPIKE      || '1000');
const VUS_SOAK           = parseInt(__ENV.VUS_SOAK       || '100');
const DURATION_HIGH      = __ENV.DURATION_HIGH           || '3m';
const DURATION_SOAK      = __ENV.DURATION_SOAK           || '10m';
const SELECTED_SCENARIO  = __ENV.SCENARIO                || 'all';

// SLO thresholds (configurable)
const SLO_READ_P95_MS  = parseInt(__ENV.SLO_READ_P95_MS  || '500');
const SLO_WRITE_P95_MS = parseInt(__ENV.SLO_WRITE_P95_MS || '1500');
const SLO_ERROR_RATE   = parseFloat(__ENV.SLO_ERROR_RATE_PCT || '1') / 100;

// ── Custom metrics ────────────────────────────────────────────────

const readLatency          = new Trend('read_latency', true);
const writeLatency         = new Trend('write_latency', true);
const patchLatency         = new Trend('patch_latency', true);
const listPoisLatency      = new Trend('endpoint_list_pois', true);
const listAssetsLatency    = new Trend('endpoint_list_assets', true);
const listScriptsLatency   = new Trend('endpoint_list_scripts', true);
const listRendersLatency   = new Trend('endpoint_list_renders', true);
const createPoiLatency     = new Trend('endpoint_create_poi', true);
const createAssetLatency   = new Trend('endpoint_create_asset', true);
const patchPoiLatency      = new Trend('endpoint_patch_poi', true);
const healthLatency        = new Trend('endpoint_health', true);
const errorRate            = new Rate('error_rate');
const errCount             = new Counter('errors_total');
const http4xx              = new Counter('http_4xx');
const http5xx              = new Counter('http_5xx');
const timeoutCount         = new Counter('timeouts_total');
const requestsOk           = new Counter('requests_ok');

// ── Thresholds ────────────────────────────────────────────────────

export const options = {
  thresholds: {
    'read_latency':    [`p(95)<${SLO_READ_P95_MS}`],
    'write_latency':   [`p(95)<${SLO_WRITE_P95_MS}`],
    'patch_latency':   [`p(95)<${SLO_WRITE_P95_MS}`],
    'error_rate':      [`rate<${SLO_ERROR_RATE}`],
    'http_req_failed': ['rate<0.01'],
    'http_req_duration': ['p(95)<2000'],  // global safety net
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
        { duration: '30s', target: Math.floor(VUS_HIGH / 2) },
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
        { duration: '10s',  target: Math.floor(VUS_SPIKE / 2) },
        { duration: '20s',  target: VUS_SPIKE },
        { duration: '30s',  target: VUS_SPIKE },
        { duration: '10s',  target: 0 },
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
      startTime: '7m30s',
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

// ── Shared state: cache of created POI IDs for PATCH operations ──

const createdPoiIds = [];
const createdAssetIds = [];

// ── Setup: create seed data for reads ─────────────────────────────

export function setup() {
  const hdrs = headers();
  const seedPois = [];

  // Create 5 seed POIs so reads have data from the start
  for (let i = 0; i < 5; i++) {
    const payload = JSON.stringify({
      name: `k6-seed-${i}-${randomString(6)}`,
      description: `Seed POI ${i} for load testing`,
      lat: 48.85 + Math.random() * 0.1,
      lon: 2.30 + Math.random() * 0.1,
      poi_type: ['villa', 'apartment', 'office'][i % 3],
      tags: ['k6', 'seed'],
    });
    const res = http.post(`${POI_URL}/pois`, payload, { headers: hdrs, timeout: '10s' });
    if (res.status === 201) {
      try {
        const body = JSON.parse(res.body);
        if (body.id) seedPois.push(body.id);
      } catch (e) { /* ignore */ }
    }
  }

  return { seedPoiIds: seedPois };
}

// ── Workload functions ────────────────────────────────────────────

// 80% reads / 20% writes (10% POI create + 5% asset create + 5% patch)
export function mixedWorkload(data) {
  // Inject seed POI IDs if available
  if (data && data.seedPoiIds) {
    for (const id of data.seedPoiIds) {
      if (!createdPoiIds.includes(id)) createdPoiIds.push(id);
    }
  }

  const r = Math.random();
  if (r < 0.80) {
    doRead();
  } else if (r < 0.90) {
    doWritePoi();
  } else if (r < 0.95) {
    doWriteAsset();
  } else {
    doPatch();
  }
  sleep(0.1 + Math.random() * 0.3);
}

// 90% reads / 10% writes (5% POI create + 2% asset create + 3% patch)
export function readHeavy(data) {
  if (data && data.seedPoiIds) {
    for (const id of data.seedPoiIds) {
      if (!createdPoiIds.includes(id)) createdPoiIds.push(id);
    }
  }

  const r = Math.random();
  if (r < 0.90) {
    doRead();
  } else if (r < 0.95) {
    doWritePoi();
  } else if (r < 0.97) {
    doWriteAsset();
  } else {
    doPatch();
  }
  sleep(0.05 + Math.random() * 0.15);
}

// ── Read operations ───────────────────────────────────────────────

function doRead() {
  const ops = [listPois, listAssets, listScripts, listRenders, getHealth];
  const weights = [35, 25, 15, 10, 15];
  let total = 0;
  const r = Math.random() * 100;
  for (let i = 0; i < ops.length; i++) {
    total += weights[i];
    if (r < total) {
      ops[i]();
      return;
    }
  }
  ops[0]();
}

function listPois() {
  group('GET /pois', () => {
    const page = Math.floor(Math.random() * 5) + 1;
    const pageSize = [10, 20, 50][Math.floor(Math.random() * 3)];
    let qs = `page=${page}&page_size=${pageSize}`;

    // Occasionally add filters (realistic usage patterns)
    if (Math.random() < 0.3) {
      qs += '&status=draft';
    } else if (Math.random() < 0.2) {
      qs += '&poi_type=villa';
    } else if (Math.random() < 0.1) {
      qs += '&q=k6';  // search query
    }

    const res = http.get(`${POI_URL}/pois?${qs}`, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    listPoisLatency.add(res.timings.duration);
    trackResponse(res, 'list_pois');

    // Validate response structure
    if (res.status === 200) {
      try {
        const body = JSON.parse(res.body);
        check(body, {
          'list_pois has items': (b) => Array.isArray(b.items),
          'list_pois has total': (b) => typeof b.total === 'number',
          'list_pois has page': (b) => typeof b.page === 'number',
        });
      } catch (e) { /* ignore parse errors */ }
    }
  });
}

function listAssets() {
  group('GET /assets', () => {
    let url = `${ASSET_URL}/assets?page=1&page_size=50`;
    if (createdPoiIds.length > 0) {
      const pid = createdPoiIds[Math.floor(Math.random() * createdPoiIds.length)];
      url = `${ASSET_URL}/assets?poi_id=${pid}&page=1&page_size=50`;
    }
    const res = http.get(url, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    listAssetsLatency.add(res.timings.duration);
    trackResponse(res, 'list_assets');
  });
}

function listScripts() {
  group('GET /scripts', () => {
    let url = `${SCRIPT_URL}/scripts?page=1&page_size=20`;
    if (createdPoiIds.length > 0) {
      const pid = createdPoiIds[Math.floor(Math.random() * createdPoiIds.length)];
      url = `${SCRIPT_URL}/scripts?poi_id=${pid}&page=1&page_size=20`;
    }
    const res = http.get(url, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    listScriptsLatency.add(res.timings.duration);
    trackResponse(res, 'list_scripts');
  });
}

function listRenders() {
  group('GET /renders', () => {
    let url = `${RENDER_URL}/renders?page=1&page_size=20`;
    if (createdPoiIds.length > 0) {
      const pid = createdPoiIds[Math.floor(Math.random() * createdPoiIds.length)];
      url = `${RENDER_URL}/renders?poi_id=${pid}&page=1&page_size=20`;
    }
    const res = http.get(url, { headers: headers(), timeout: '10s' });
    readLatency.add(res.timings.duration);
    listRendersLatency.add(res.timings.duration);
    trackResponse(res, 'list_renders');
  });
}

function getHealth() {
  group('GET /healthz', () => {
    const urls = [POI_URL, ASSET_URL, SCRIPT_URL, TRANSCRIPTION_URL, RENDER_URL];
    const url = urls[Math.floor(Math.random() * urls.length)];
    const res = http.get(`${url}/healthz`, { headers: headers(), timeout: '5s' });
    readLatency.add(res.timings.duration);
    healthLatency.add(res.timings.duration);

    if (res.status === 200) {
      check(res.json(), {
        'health status ok': (j) => j.status === 'ok',
      });
    }
    trackResponse(res, 'health');
  });
}

// ── Write operations ──────────────────────────────────────────────

function doWritePoi() {
  group('POST /pois', () => {
    const poiTypes = ['villa', 'apartment', 'office', 'restaurant', 'hotel', 'warehouse'];
    const payload = JSON.stringify({
      name: `k6-Load-${randomString(8)}`,
      description: `Load test POI – stress testing ${new Date().toISOString()}`,
      address: `${Math.floor(Math.random() * 200)} Avenue de la République, Paris`,
      lat: 48.8 + Math.random() * 0.1,
      lon: 2.3 + Math.random() * 0.1,
      poi_type: poiTypes[Math.floor(Math.random() * poiTypes.length)],
      tags: ['k6', 'load-test'],
      metadata: {
        surface_m2: Math.floor(50 + Math.random() * 400),
        price_eur: Math.floor(100000 + Math.random() * 5000000),
        bedrooms: Math.floor(1 + Math.random() * 6),
        energy_class: ['A', 'B', 'C', 'D'][Math.floor(Math.random() * 4)],
      },
    });

    const res = http.post(`${POI_URL}/pois`, payload, { headers: headers(), timeout: '15s' });
    writeLatency.add(res.timings.duration);
    createPoiLatency.add(res.timings.duration);

    const ok = trackResponse(res, 'create_poi');
    if (ok) {
      try {
        const body = JSON.parse(res.body);
        if (body.id) {
          createdPoiIds.push(body.id);
          if (createdPoiIds.length > 100) createdPoiIds.shift();

          // Validate response schema
          check(body, {
            'create_poi has id': (b) => typeof b.id === 'string' && b.id.length === 36,
            'create_poi status draft': (b) => b.status === 'draft',
            'create_poi version 1': (b) => b.version === 1,
          });
        }
      } catch (e) { /* ignore parse errors */ }
    }
  });
}

function doWriteAsset() {
  group('POST /assets', () => {
    // Need a POI ID first
    if (createdPoiIds.length === 0) {
      doWritePoi();
      if (createdPoiIds.length === 0) return;
    }

    const poiId = createdPoiIds[Math.floor(Math.random() * createdPoiIds.length)];
    const types = ['photo', 'video', 'raw_video', 'document'];
    const mimeTypes = {
      'photo': 'image/jpeg',
      'video': 'video/mp4',
      'raw_video': 'video/mp4',
      'document': 'application/pdf',
    };
    const assetType = types[Math.floor(Math.random() * types.length)];

    const payload = JSON.stringify({
      poi_id: poiId,
      name: `k6-asset-${randomString(8)}.${assetType === 'photo' ? 'jpg' : 'mp4'}`,
      asset_type: assetType,
      description: `k6 load test asset – ${assetType}`,
      file_path: `/data/assets/k6-${randomString(12)}`,
      mime_type: mimeTypes[assetType] || 'application/octet-stream',
      file_size: Math.floor(1000 + Math.random() * 50000000),
    });

    const res = http.post(`${ASSET_URL}/assets`, payload, { headers: headers(), timeout: '15s' });
    writeLatency.add(res.timings.duration);
    createAssetLatency.add(res.timings.duration);

    const ok = trackResponse(res, 'create_asset');
    if (ok) {
      try {
        const body = JSON.parse(res.body);
        if (body.id) {
          createdAssetIds.push(body.id);
          if (createdAssetIds.length > 50) createdAssetIds.shift();
        }
      } catch (e) { /* ignore */ }
    }
  });
}

function doPatch() {
  group('PATCH /pois/{id}', () => {
    if (createdPoiIds.length === 0) {
      doWritePoi();
      if (createdPoiIds.length === 0) return;
    }

    const poiId = createdPoiIds[Math.floor(Math.random() * createdPoiIds.length)];
    const payload = JSON.stringify({
      description: `Updated by k6 at ${new Date().toISOString()} – ${randomString(16)}`,
      tags: ['k6', 'updated', 'load-test'],
      metadata: {
        last_updated: new Date().toISOString(),
        update_source: 'k6-load-test',
      },
    });

    const res = http.patch(`${POI_URL}/pois/${poiId}`, payload, { headers: headers(), timeout: '15s' });
    writeLatency.add(res.timings.duration);
    patchLatency.add(res.timings.duration);
    patchPoiLatency.add(res.timings.duration);
    trackResponse(res, 'patch_poi');
  });
}

// ── Response tracking ─────────────────────────────────────────────

function trackResponse(res, opName) {
  const ok = check(res, {
    [`${opName} status ok`]: (r) => r.status >= 200 && r.status < 400,
  });

  if (!ok) {
    errorRate.add(1);
    errCount.add(1);

    if (res.status >= 400 && res.status < 500) {
      http4xx.add(1);
    }
    if (res.status >= 500) {
      http5xx.add(1);
    }
    if (res.timings.duration > 10000) {
      timeoutCount.add(1);
    }
  } else {
    errorRate.add(0);
    requestsOk.add(1);
  }

  return ok;
}

// ── Summary output ────────────────────────────────────────────────

export function handleSummary(data) {
  const outDir = __ENV.ARTIFACTS_DIR || 'artifacts/qa';

  // Build structured summary
  const summary = {
    generated_at: new Date().toISOString(),
    k6_version: '0.47+',
    configuration: {
      vus_high: VUS_HIGH,
      vus_spike: VUS_SPIKE,
      vus_soak: VUS_SOAK,
      duration_high: DURATION_HIGH,
      duration_soak: DURATION_SOAK,
      scenario: SELECTED_SCENARIO,
      slo_read_p95_ms: SLO_READ_P95_MS,
      slo_write_p95_ms: SLO_WRITE_P95_MS,
      slo_error_rate_pct: SLO_ERROR_RATE * 100,
    },
    metrics: data.metrics || {},
    root_group: data.root_group || {},
    state: data.state || {},
  };

  // Extract per-endpoint stats
  const endpointMetrics = {};
  const metricNames = [
    'endpoint_list_pois', 'endpoint_list_assets', 'endpoint_list_scripts',
    'endpoint_list_renders', 'endpoint_create_poi', 'endpoint_create_asset',
    'endpoint_patch_poi', 'endpoint_health',
  ];

  for (const name of metricNames) {
    const m = data.metrics[name];
    if (m && m.values) {
      endpointMetrics[name] = {
        p50: m.values.med || 0,
        p95: m.values['p(95)'] || 0,
        p99: m.values['p(99)'] || 0,
        avg: m.values.avg || 0,
        min: m.values.min || 0,
        max: m.values.max || 0,
        count: m.values.count || 0,
      };
    }
  }
  summary.endpoint_metrics = endpointMetrics;

  // Error breakdown
  summary.error_breakdown = {
    total_errors: (data.metrics.errors_total || {}).values?.count || 0,
    http_4xx: (data.metrics.http_4xx || {}).values?.count || 0,
    http_5xx: (data.metrics.http_5xx || {}).values?.count || 0,
    timeouts: (data.metrics.timeouts_total || {}).values?.count || 0,
    error_rate_pct: ((data.metrics.error_rate || {}).values?.rate || 0) * 100,
    requests_ok: (data.metrics.requests_ok || {}).values?.count || 0,
  };

  // SLO compliance
  const readP95 = (data.metrics.read_latency || {}).values?.['p(95)'] || 0;
  const writeP95 = (data.metrics.write_latency || {}).values?.['p(95)'] || 0;
  const errRatePct = ((data.metrics.error_rate || {}).values?.rate || 0) * 100;

  summary.slo_compliance = {
    read_p95_ok: readP95 < SLO_READ_P95_MS,
    read_p95_actual_ms: readP95,
    read_p95_threshold_ms: SLO_READ_P95_MS,
    write_p95_ok: writeP95 < SLO_WRITE_P95_MS,
    write_p95_actual_ms: writeP95,
    write_p95_threshold_ms: SLO_WRITE_P95_MS,
    error_rate_ok: errRatePct < (SLO_ERROR_RATE * 100),
    error_rate_actual_pct: errRatePct,
    error_rate_threshold_pct: SLO_ERROR_RATE * 100,
  };

  return {
    'stdout': textSummary(data, summary),
    [`${outDir}/k6-summary.json`]: JSON.stringify(summary, null, 2),
  };
}

function textSummary(data, summary) {
  const lines = [];
  lines.push('');
  lines.push('═══════════════════════════════════════════════════════');
  lines.push('  k6 Load Test Summary');
  lines.push('═══════════════════════════════════════════════════════');

  const reqs = (data.metrics.http_reqs || {}).values?.count || 0;
  const dur = (data.metrics.http_req_duration || {}).values || {};
  lines.push(`  Total requests: ${reqs}`);
  lines.push(`  HTTP req duration: avg=${(dur.avg || 0).toFixed(0)}ms p95=${(dur['p(95)'] || 0).toFixed(0)}ms p99=${(dur['p(99)'] || 0).toFixed(0)}ms`);

  const slo = summary.slo_compliance || {};
  lines.push('');
  lines.push('  SLO Compliance:');
  lines.push(`    Read  p95: ${slo.read_p95_ok ? '✅' : '❌'} ${(slo.read_p95_actual_ms || 0).toFixed(0)}ms (threshold: ${SLO_READ_P95_MS}ms)`);
  lines.push(`    Write p95: ${slo.write_p95_ok ? '✅' : '❌'} ${(slo.write_p95_actual_ms || 0).toFixed(0)}ms (threshold: ${SLO_WRITE_P95_MS}ms)`);
  lines.push(`    Err rate:  ${slo.error_rate_ok ? '✅' : '❌'} ${(slo.error_rate_actual_pct || 0).toFixed(2)}% (threshold: ${(SLO_ERROR_RATE * 100).toFixed(1)}%)`);

  const eb = summary.error_breakdown || {};
  if (eb.total_errors > 0) {
    lines.push('');
    lines.push(`  Errors: ${eb.total_errors} total (4xx=${eb.http_4xx}, 5xx=${eb.http_5xx}, timeouts=${eb.timeouts})`);
  }

  lines.push('═══════════════════════════════════════════════════════');
  lines.push('');
  return lines.join('\n');
}

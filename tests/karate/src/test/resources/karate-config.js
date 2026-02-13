function fn() {
  // ── Environment ────────────────────────────────────────────────────
  var env = karate.env || 'local';
  karate.log('karate.env =', env);

  // ── Base URLs per service (override via environment variables) ─────
  var config = {
    poiBaseUrl:            karate.properties['POI_BASE_URL']            || java.lang.System.getenv('POI_BASE_URL')            || 'http://localhost:8001',
    assetBaseUrl:          karate.properties['ASSET_BASE_URL']          || java.lang.System.getenv('ASSET_BASE_URL')          || 'http://localhost:8002',
    scriptBaseUrl:         karate.properties['SCRIPT_BASE_URL']         || java.lang.System.getenv('SCRIPT_BASE_URL')         || 'http://localhost:8003',
    transcriptionBaseUrl:  karate.properties['TRANSCRIPTION_BASE_URL']  || java.lang.System.getenv('TRANSCRIPTION_BASE_URL')  || 'http://localhost:8004',
    renderBaseUrl:         karate.properties['RENDER_BASE_URL']         || java.lang.System.getenv('RENDER_BASE_URL')         || 'http://localhost:8005',

    // API key – header included in all requests
    apiKey: karate.properties['API_KEY'] || java.lang.System.getenv('API_KEY') || 'dev-api-key',

    // Timeouts
    connectTimeout: 10000,
    readTimeout:    30000,

    // Polling defaults for async operations
    pollRetryCount:    40,
    pollIntervalMs:    3000
  };

  // ── Per-environment overrides ──────────────────────────────────────
  if (env === 'k8s') {
    // When running against a Kubernetes cluster via ingress / port-forward
    var k8sHost = java.lang.System.getenv('K8S_HOST') || 'localhost';
    config.poiBaseUrl           = 'http://' + k8sHost + ':8001';
    config.assetBaseUrl         = 'http://' + k8sHost + ':8002';
    config.scriptBaseUrl        = 'http://' + k8sHost + ':8003';
    config.transcriptionBaseUrl = 'http://' + k8sHost + ':8004';
    config.renderBaseUrl        = 'http://' + k8sHost + ':8005';
  }

  // ── Common headers (injected in every request) ─────────────────────
  karate.configure('headers', {
    'Content-Type': 'application/json',
    'X-API-Key':    config.apiKey
  });

  karate.configure('connectTimeout', config.connectTimeout);
  karate.configure('readTimeout',    config.readTimeout);

  // Disable SSL cert verification for local dev
  karate.configure('ssl', true);

  return config;
}


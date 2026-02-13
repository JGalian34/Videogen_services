# Real Estate POI Video Platform

> **Monorepo** – 5 microservices FastAPI pour la gestion de POIs immobiliers et la generation automatisee de videos marketing.

---

## Vision

Cette plateforme permet de :

1. **Enregistrer des Points d'Interet** (biens immobiliers) avec un workflow de validation
2. **Attacher des assets** (photos, plans, videos brutes) a chaque POI
3. **Generer un script video** structure scene par scene via NLP (stub/OpenAI)
4. **Transcrire** les videos brutes (pipeline STT stub)
5. **Rendre** les scenes video via Runway ML (stub par defaut, live si API key fournie)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Real Estate POI Video Platform                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │
│   │  poi-service  │    │asset-service │    │script-service│                 │
│   │   :8001       │    │   :8002      │    │   :8003      │                 │
│   │               │    │              │    │              │                 │
│   │  CRUD POI     │    │  CRUD Assets │    │  Generate    │                 │
│   │  Workflow     │    │  File refs   │    │  VideoScript │                 │
│   │  Search       │    │              │    │  NLP stub    │                 │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                 │
│          │                   │                   │                          │
│          │   poi.events      │  asset.events     │  video.events           │
│          ▼                   ▼                   ▼                          │
│   ┌─────────────────────────────────────────────────────────┐              │
│   │                    Redpanda (Kafka)                      │              │
│   │  Topics: poi.events | asset.events | video.events | dlq │              │
│   └─────────────────────────┬───────────────────────────────┘              │
│                             │                                               │
│                    ┌────────┴────────┐                                      │
│                    ▼                 ▼                                      │
│   ┌──────────────────────┐  ┌──────────────────────┐                       │
│   │transcription-service │  │  render-service       │                       │
│   │   :8004              │  │   :8005               │                       │
│   │                      │  │                       │                       │
│   │  STT Pipeline (stub) │  │  Runway Client        │                       │
│   │  Job: start → done   │  │  stub / live mode     │                       │
│   │                      │  │  Event consumer       │                       │
│   └──────────────────────┘  └───────────────────────┘                       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────┐              │
│   │                  PostgreSQL :5433                        │              │
│   │  DBs: poi_service | asset_service | script_service      │              │
│   │       transcription_service | render_service            │              │
│   └─────────────────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flux de donnees

```
1. CREATE POI ──▶ poi-service (draft)
2. VALIDATE    ──▶ poi-service (validated)
3. PUBLISH     ──▶ poi-service (published) ──▶ poi.events
4. ADD ASSETS  ──▶ asset-service            ──▶ asset.events
5. GENERATE    ──▶ script-service           ──▶ video.events (script.generated)
       │                                          │
       │  HTTP (reads POI + assets)               │
       ▼                                          ▼
6. TRANSCRIBE  ──▶ transcription-service    render-service (auto-consumes)
       │              │                           │
       ▼              ▼                           ▼
   video.events   transcription.completed    render.completed
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Langage | Python 3.12 |
| Framework API | FastAPI |
| Schemas | Pydantic v2 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Base de donnees | PostgreSQL 16 |
| Event streaming | Redpanda (Kafka compatible) |
| Auth | API Key simple (`X-API-Key`) |
| Observabilite | Logs JSON + correlation_id |
| Tests | pytest (unit + integration) |
| Lint/Format | ruff + black |
| CI | GitHub Actions |
| Conteneurs | Docker + docker-compose |

---

## Arborescence

```
real-estate-poi-video-platform/
├── README.md
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── .github/workflows/
│   ├── ci.yml                  # Lint + tests
│   ├── docker-publish.yml      # Build & push images GHCR
│   └── e2e.yml                 # Karate E2E nightly
│
├── libs/
│   ├── contracts/              # Schemas d'events Pydantic (DomainEvent)
│   │   └── contracts/events.py
│   └── common/                 # Utils partages
│       └── common/
│           ├── config.py       # Helpers env vars
│           ├── errors.py       # AppError, NotFoundError, WorkflowError
│           ├── http_client.py  # ServiceClient (propagation correlation_id)
│           ├── kafka.py        # Shared Kafka publisher + DLQ
│           ├── logging.py      # JSON logging + correlation
│           └── middleware/
│               ├── auth.py     # API Key middleware
│               └── correlation.py
│
├── services/
│   ├── poi-service/            # Port 8001
│   ├── asset-service/          # Port 8002
│   ├── script-service/         # Port 8003
│   ├── transcription-service/  # Port 8004
│   └── render-service/         # Port 8005
│       (each with: app/{api/routers,core,db,services,integrations}, tests/, alembic/)
│
├── tests/karate/               # E2E functional tests (Karate + Maven)
│   ├── pom.xml
│   └── src/test/resources/
│       ├── karate-config.js
│       └── features/           # 7 feature files
│
├── deploy/k8s/                 # Kubernetes manifests (Kustomize)
│   ├── base/                   # Namespace, services, infra
│   └── overlays/dev/           # GHCR images + ingress
│
├── scripts/
│   ├── init-databases.sql
│   ├── seed.sh
│   └── wait-for-it.sh
│
└── data/assets/                # Volume local pour stockage objet simule
```

---

## Demarrage rapide

### Pre-requis

- Docker + Docker Compose v2
- (Optionnel) Python 3.12 pour dev local

### Lancer tout en 1 commande

```bash
make up
```

Cela va :
1. Builder les 5 services
2. Demarrer PostgreSQL + Redpanda
3. Creer les 5 bases de donnees
4. Appliquer les migrations Alembic
5. Exposer les services sur les ports 8001-8005

### Verifier

```bash
make smoke-test
```

### Seed (donnees de demo)

```bash
make seed
```

Cree : 1 POI (Villa Mediterranee, Montpellier) + 2 assets + 1 script video + 1 transcription.

### Arreter

```bash
make down      # stop
make down-v    # stop + supprime les volumes
```

---

## Endpoints par service

### POI Service (:8001)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/pois` | Creer un POI |
| GET | `/pois` | Lister (filtres: query, status, poi_type) |
| GET | `/pois/{id}` | Detail |
| PATCH | `/pois/{id}` | Modifier |
| POST | `/pois/{id}/validate` | Workflow: draft → validated |
| POST | `/pois/{id}/publish` | Workflow: validated → published |
| POST | `/pois/{id}/archive` | Workflow: published → archived |
| GET | `/healthz` | Health check |
| GET | `/readyz` | Readiness (DB check) |

### Asset Service (:8002)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/assets` | Creer un asset (metadata + ref fichier) |
| GET | `/assets?poi_id=` | Lister par POI |
| GET | `/assets/{id}` | Detail |
| PATCH | `/assets/{id}` | Modifier |
| GET | `/healthz` `/readyz` | Health checks |

### Script Service (:8003)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/scripts/generate?poi_id=` | Generer un script video |
| GET | `/scripts?poi_id=` | Lister par POI |
| GET | `/scripts/{id}` | Detail |
| GET | `/healthz` `/readyz` | Health checks |

### Transcription Service (:8004)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/transcriptions/start?poi_id=&asset_video_id=` | Demarrer |
| GET | `/transcriptions?poi_id=` | Lister |
| GET | `/transcriptions/{id}` | Detail |
| GET | `/healthz` `/readyz` | Health checks |

### Render Service (:8005)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/renders?poi_id=` | Lister les jobs |
| GET | `/renders/{id}` | Detail (avec scenes) |
| POST | `/renders/retry/{id}` | Relancer un render echoue |
| GET | `/healthz` `/readyz` | Health checks |

---

## Exemples curl

```bash
API_KEY="dev-api-key"

# 1) Creer un POI
curl -X POST http://localhost:8001/pois \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "name": "Appartement Haussmannien – Paris 8e",
    "description": "Magnifique 4 pieces de 120m2 avec moulures et parquet",
    "address": "15 Avenue Montaigne, 75008 Paris",
    "lat": 48.8660,
    "lon": 2.3042,
    "poi_type": "apartment",
    "tags": ["haussmann", "luxury", "paris"]
  }'

# 2) Valider le POI
curl -X POST http://localhost:8001/pois/{POI_ID}/validate \
  -H "X-API-Key: $API_KEY"

# 3) Publier
curl -X POST http://localhost:8001/pois/{POI_ID}/publish \
  -H "X-API-Key: $API_KEY"

# 4) Ajouter un asset
curl -X POST http://localhost:8002/assets \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "poi_id": "{POI_ID}",
    "name": "salon-principal.jpg",
    "asset_type": "photo",
    "file_path": "/data/assets/salon-principal.jpg",
    "mime_type": "image/jpeg"
  }'

# 5) Generer le script video
curl -X POST "http://localhost:8003/scripts/generate?poi_id={POI_ID}" \
  -H "X-API-Key: $API_KEY"

# 6) Lancer une transcription
curl -X POST "http://localhost:8004/transcriptions/start?poi_id={POI_ID}&asset_video_id={ASSET_ID}" \
  -H "X-API-Key: $API_KEY"

# 7) Voir les renders (auto-crees via event consumer)
curl http://localhost:8005/renders?poi_id={POI_ID} \
  -H "X-API-Key: $API_KEY"
```

---

## Communication inter-services

### Synchrone (HTTP)
- `script-service` → `poi-service` (GET /pois/{id})
- `script-service` → `asset-service` (GET /assets?poi_id=)

### Asynchrone (Redpanda / Kafka)

| Topic | Producteur | Evenements |
|-------|-----------|------------|
| `poi.events` | poi-service | poi.created, poi.updated, poi.validated, poi.published, poi.archived |
| `asset.events` | asset-service | asset.created, asset.updated |
| `video.events` | script/transcription/render | script.generated, transcription.completed, render.scene.generated, render.completed |
| `dlq.events` | (reserve) | Dead letter queue |

### Format d'evenement (DomainEvent)

```json
{
  "event_id": "uuid",
  "event_type": "poi.created",
  "occurred_at": "2026-02-13T10:00:00Z",
  "schema_version": 1,
  "correlation_id": "uuid",
  "payload": { ... }
}
```

---

## Qualite & Observabilite

- **Logs JSON** avec `correlation_id` propage entre services
- **Error handlers** uniformes sur tous les services (AppError → 400, NotFoundError → 404, WorkflowError → 409)
- **API Key** configurable via `API_KEY` env var (header `X-API-Key`)
- **Health checks** : `/healthz` (liveness) + `/readyz` (DB connectivity)

---

## Tests

```bash
# Localement (necessite libs installees)
make test

# Ou par service
cd services/poi-service && python -m pytest tests/ -v
```

| Service | Tests couverts |
|---------|---------------|
| poi-service | create, list, get, update, validate, publish, archive, auth |
| asset-service | create, list by poi, get, update |
| script-service | generate (mock HTTP clients), list |
| transcription-service | start, list, get |
| render-service | consume event → create job, list, healthz |

---

## E2E Tests (Karate)

> **Stack** : [Karate](https://karatelabs.github.io/karate/) (JUnit 5 + Maven) – tests fonctionnels E2E sans code Java custom.

### Structure

```
tests/karate/
├── pom.xml
├── src/test/java/karate/
│   └── KarateRunner.java
└── src/test/resources/
    ├── karate-config.js          # URLs, API key, timeouts
    ├── logback-test.xml
    └── features/
        ├── health.feature            # @smoke  – /healthz + /readyz ×5
        ├── poi.feature               # @regression – CRUD + workflow
        ├── assets.feature            # @regression – create + list + update
        ├── script.feature            # @regression – generate + verify scenes
        ├── transcription.feature     # @regression – start + poll completion
        ├── render.feature            # @regression – event-driven render
        └── e2e_video_pipeline.feature # @e2e – full pipeline end-to-end
```

### Exécution

```bash
# Contre docker-compose (démarre les services automatiquement)
make e2e

# Contre un cluster Kubernetes (port-forward ou ingress)
make e2e-k8s

# Seulement les smoke tests
cd tests/karate && mvn test -Dkarate.options="--tags @smoke"

# Seulement le pipeline E2E complet
cd tests/karate && mvn test -Dkarate.options="--tags @e2e"
```

### Configuration

| Variable d'environnement | Default | Description |
|--------------------------|---------|-------------|
| `POI_BASE_URL` | `http://localhost:8001` | Base URL poi-service |
| `ASSET_BASE_URL` | `http://localhost:8002` | Base URL asset-service |
| `SCRIPT_BASE_URL` | `http://localhost:8003` | Base URL script-service |
| `TRANSCRIPTION_BASE_URL` | `http://localhost:8004` | Base URL transcription-service |
| `RENDER_BASE_URL` | `http://localhost:8005` | Base URL render-service |
| `API_KEY` | `dev-api-key` | Clé API injectée dans `X-API-Key` |

### Polling (pas de sleep aveugle)

Les scénarios async (`e2e_video_pipeline.feature`, `render.feature`) utilisent le mécanisme Karate `retry until` :
- **40 tentatives** × **3 secondes** = **120s** max de polling
- Condition d'arrêt explicite (ex: `response.status == 'completed'`)
- Pas de flakiness : le test s'arrête dès que la condition est remplie

### Rapports

Après exécution, les rapports Karate (HTML + JSON) sont dans :
```
tests/karate/target/karate-reports/karate-summary.html
```
En CI, ils sont uploadés en artifacts GitHub Actions.

---

## Kubernetes Deploy

> **Outil** : [Kustomize](https://kustomize.io/) (natif kubectl) – pas besoin de Helm.

### Architecture K8s

```
┌─ namespace: poi-video-platform ──────────────────────────────────┐
│                                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ postgres  │  │   redpanda   │  │   ingress    │               │
│  │  (infra)  │  │   (infra)    │  │   (nginx)    │               │
│  └──────────┘  └──────────────┘  └──────┬───────┘               │
│                                          │                        │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌────────────┐
│    │   poi    │ │  asset   │ │  script  │ │transcription │ │  render    │
│    │ service  │ │ service  │ │ service  │ │  service     │ │  service   │
│    │  :8001   │ │  :8002   │ │  :8003   │ │  :8004       │ │  :8005     │
│    └──────────┘ └──────────┘ └──────────┘ └──────────────┘ └────────────┘
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Structure des manifests

```
deploy/k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── postgres.yaml              # Deployment + Service + init ConfigMap
│   ├── redpanda.yaml              # Deployment + Service
│   ├── poi-service.yaml           # Deployment + Service
│   ├── asset-service.yaml         # Deployment + Service
│   ├── script-service.yaml        # Deployment + Service
│   ├── transcription-service.yaml # Deployment + Service
│   └── render-service.yaml        # Deployment + Service
└── overlays/
    └── dev/
        ├── kustomization.yaml     # GHCR images + imagePullPolicy: Always
        └── ingress.yaml           # Nginx ingress routes
```

### Commandes

```bash
# Déployer (kustomize overlay dev)
make k8s-up

# Supprimer le namespace
make k8s-down

# Voir les logs d'un service
make k8s-logs SERVICE=poi-service

# Port-forward pour accès local
make k8s-port-forward SERVICE=poi-service PORT=8001

# Lancer les tests Karate contre le cluster
make e2e-k8s
```

### Stratégie d'images

| Registre | Tag | Usage |
|----------|-----|-------|
| GHCR | `:sha-<7chars>` | Immutable – pour GitOps (ArgoCD/Flux) |
| GHCR | `:latest` | Mutable – pour dev rapide (`imagePullPolicy: Always`) |

En CI (`.github/workflows/docker-publish.yml`), chaque push sur `main` :
1. Build les 5 images en parallèle (matrix)
2. Push vers GHCR avec les 2 tags
3. (Optionnel) Met à jour le tag dans `kustomization.yaml`

### GitOps (optionnel)

Pour un déploiement automatique des nouvelles images :

**Option A – ArgoCD Image Updater** :
```yaml
# Annotation sur l'Application ArgoCD
argocd-image-updater.argoproj.io/image-list: |
  poi=ghcr.io/OWNER/real-estate-poi-video-platform/poi-service
  asset=ghcr.io/OWNER/real-estate-poi-video-platform/asset-service
  ...
argocd-image-updater.argoproj.io/poi.update-strategy: latest
```

**Option B – Flux Image Automation** :
```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: poi-service
spec:
  imageRepositoryRef:
    name: poi-service
  filterTags:
    pattern: '^sha-[a-f0-9]{7}$'
  policy:
    alphabetical:
      order: desc
```

### Probes & Resources

Chaque service est configuré avec :
- **Liveness** : `GET /healthz` (initialDelay: 10s, period: 10s)
- **Readiness** : `GET /readyz` (initialDelay: 5s, period: 5s)
- **Resources** : requests 100m CPU / 128Mi RAM – limits 250m / 256Mi

---

## CI/CD

### Workflows GitHub Actions

| Workflow | Fichier | Déclencheur | Description |
|----------|---------|-------------|-------------|
| Lint + Tests | `ci.yml` | Push / PR | ruff + black + mypy + pytest (matrice 5 services) |
| Docker Publish | `docker-publish.yml` | Push `main` | Build & push 5 images GHCR (matrix, parallel) |
| E2E Karate | `e2e.yml` | Nightly / manual | docker-compose up → Karate tests → upload reports |

---

## Configuration

Toute la config est via variables d'environnement (12-Factor) :

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `dev-api-key` | Cle API pour l'auth |
| `POSTGRES_HOST` | `localhost` | Host PostgreSQL |
| `POSTGRES_DB` | `{service}_service` | Base par service |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Broker Redpanda |
| `LOG_LEVEL` | `INFO` | Niveau de log |
| `LOG_FORMAT` | `json` | Format: json ou text |
| `NLP_PROVIDER` | `stub` | Provider NLP: stub ou openai |
| `RUNWAY_MODE` | `stub` | Mode Runway: stub ou live |
| `RUNWAY_API_KEY` | `` | Cle API Runway (si live) |

---

## Licence

Usage interne – Projet de demonstration.


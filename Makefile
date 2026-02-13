.PHONY: help up down build logs lint format test migrate seed smoke-test clean \
       e2e e2e-k8s k8s-up k8s-down k8s-logs k8s-port-forward \
       qa qa-fast qa-e2e qa-load qa-clean

# ============================================================
# Real Estate POI Video Platform – Makefile
# ============================================================

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:' $(MAKEFILE_LIST) | grep '##' | \
		sed 's/\(^[a-zA-Z0-9_-]*\):.* ## /\1\t/' | \
		awk -F'\t' '{printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Docker ─────────────────────────────────────────────────────
up: ## Start all services (build + detach)
	docker compose up -d --build

down: ## Stop all services
	docker compose down

down-v: ## Stop all services and remove volumes
	docker compose down -v

build: ## Build all images
	docker compose build

logs: ## Follow all logs
	docker compose logs -f

# ── Quality ────────────────────────────────────────────────────
lint: ## Run ruff + black + mypy on all services
	@for svc in poi-service asset-service script-service transcription-service render-service; do \
		echo "==> Linting $$svc"; \
		cd services/$$svc && ruff check . && black --check . && mypy app/ --ignore-missing-imports --no-error-summary && cd ../..; \
	done
	@echo "==> Linting libs"
	cd libs/contracts && ruff check . && black --check .
	cd libs/common && ruff check . && black --check .

format: ## Auto-format with ruff + black
	@for svc in poi-service asset-service script-service transcription-service render-service; do \
		echo "==> Formatting $$svc"; \
		cd services/$$svc && ruff check --fix . && black . && cd ../..; \
	done
	cd libs/contracts && ruff check --fix . && black .
	cd libs/common && ruff check --fix . && black .

test: ## Run all tests
	@for svc in poi-service asset-service script-service transcription-service render-service; do \
		echo "==> Testing $$svc"; \
		cd services/$$svc && python -m pytest tests/ -v --tb=short && cd ../..; \
	done

# ── Database ───────────────────────────────────────────────────
migrate: ## Apply Alembic migrations (all services)
	docker compose exec poi-service alembic upgrade head
	docker compose exec asset-service alembic upgrade head
	docker compose exec script-service alembic upgrade head
	docker compose exec transcription-service alembic upgrade head
	docker compose exec render-service alembic upgrade head

seed: ## Seed: create 1 POI + 2 assets + generate script + transcription
	@chmod +x scripts/seed.sh
	@bash scripts/seed.sh

# ── Smoke Test ─────────────────────────────────────────────────
smoke-test: ## Hit /healthz on every service
	@echo "==> poi-service"
	@curl -sf http://localhost:8001/healthz && echo " OK" || echo " FAIL"
	@echo "==> asset-service"
	@curl -sf http://localhost:8002/healthz && echo " OK" || echo " FAIL"
	@echo "==> script-service"
	@curl -sf http://localhost:8003/healthz && echo " OK" || echo " FAIL"
	@echo "==> transcription-service"
	@curl -sf http://localhost:8004/healthz && echo " OK" || echo " FAIL"
	@echo "==> render-service"
	@curl -sf http://localhost:8005/healthz && echo " OK" || echo " FAIL"

# ── E2E (Karate) ──────────────────────────────────────────────────
E2E_DIR := tests/karate

e2e: up ## Run Karate E2E tests against docker-compose stack
	@echo "==> Waiting for services to be ready..."
	@for port in 8001 8002 8003 8004 8005; do \
		until curl -sf http://localhost:$$port/healthz >/dev/null 2>&1; do \
			sleep 2; \
		done; \
		echo "    localhost:$$port OK"; \
	done
	@echo "==> Running Karate tests"
	cd $(E2E_DIR) && mvn test -Dkarate.env=local \
		-DPOI_BASE_URL=http://localhost:8001 \
		-DASSET_BASE_URL=http://localhost:8002 \
		-DSCRIPT_BASE_URL=http://localhost:8003 \
		-DTRANSCRIPTION_BASE_URL=http://localhost:8004 \
		-DRENDER_BASE_URL=http://localhost:8005 \
		-DAPI_KEY=dev-api-key

e2e-k8s: ## Run Karate E2E tests against K8s (set K8S_HOST or port-forward first)
	@echo "==> Running Karate tests against Kubernetes"
	cd $(E2E_DIR) && mvn test -Dkarate.env=k8s \
		-DK8S_HOST=$${K8S_HOST:-localhost} \
		-DAPI_KEY=$${API_KEY:-dev-api-key}

# ── Kubernetes ────────────────────────────────────────────────────
K8S_OVERLAY  := deploy/k8s/overlays/dev
K8S_NS       := poi-video-platform

k8s-up: ## Deploy to Kubernetes (kustomize dev overlay)
	@echo "==> Applying kustomize overlay $(K8S_OVERLAY)"
	kubectl apply -k $(K8S_OVERLAY)
	@echo "==> Waiting for rollout..."
	@for svc in poi-service asset-service script-service transcription-service render-service; do \
		kubectl -n $(K8S_NS) rollout status deployment/$$svc --timeout=120s; \
	done
	@echo "All deployments ready ✓"

k8s-down: ## Delete Kubernetes namespace (removes everything)
	kubectl delete namespace $(K8S_NS) --ignore-not-found

k8s-logs: ## Stream logs (usage: make k8s-logs SERVICE=poi-service)
	@test -n "$(SERVICE)" || { echo "Usage: make k8s-logs SERVICE=<name>"; exit 1; }
	kubectl -n $(K8S_NS) logs -f -l app.kubernetes.io/name=$(SERVICE) --all-containers

k8s-port-forward: ## Port-forward a service (usage: make k8s-port-forward SERVICE=poi-service PORT=8001)
	@test -n "$(SERVICE)" || { echo "Usage: make k8s-port-forward SERVICE=<name> PORT=<port>"; exit 1; }
	@test -n "$(PORT)"    || { echo "Usage: make k8s-port-forward SERVICE=<name> PORT=<port>"; exit 1; }
	kubectl -n $(K8S_NS) port-forward svc/$(SERVICE) $(PORT):$(PORT)

# ── QA Pipeline ────────────────────────────────────────────────
QA_PY := python -m tools.qa.run

qa: ## Full QA pipeline (compose + lint + test + E2E + load → report)
	$(QA_PY) --compose --teardown

qa-fast: ## Fast QA: lint + unit tests only (no docker needed)
	$(QA_PY) --fast

qa-e2e: ## E2E HTTP tests only (services must be running)
	$(QA_PY) --e2e-only

qa-load: ## Load test only (services must be running, requires k6)
	$(QA_PY) --load-only

qa-clean: ## Tear down stack + remove volumes + artifacts
	docker compose down -v
	rm -rf artifacts/qa/*.json artifacts/qa/*.md artifacts/qa/*.xml

# ── Cleanup ────────────────────────────────────────────────────
clean: ## Remove __pycache__, .pyc, .egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true


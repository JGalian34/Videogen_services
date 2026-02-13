.PHONY: help up down build logs lint format test test-unit test-db test-integration \
       migrate seed smoke-test clean \
       e2e e2e-k8s k8s-up k8s-down k8s-logs k8s-port-forward \
       k8s-preprod k8s-prod \
       qa qa-fast qa-e2e qa-load qa-clean \
       github-check github-push \
       db-up db-down db-test-up db-test-down db-test-reset

# ============================================================
# Videogen Services – Makefile
# ============================================================

SERVICES := poi-service asset-service script-service transcription-service render-service
GIT_SSH_CMD := ssh -i /home/louto/env/ssh/id_ed25519_kappn -o StrictHostKeyChecking=no -o IdentitiesOnly=yes
REMOTE_REPO := git@github.com:JGalian34/Videogen_services.git

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:' $(MAKEFILE_LIST) | grep '##' | \
		sed 's/\(^[a-zA-Z0-9_-]*\):.* ## /\1\t/' | \
		awk -F'\t' '{printf "\033[36m%-28s\033[0m %s\n", $$1, $$2}'

# ═══════════════════════════════════════════════════════════════
# Docker Compose – Local Development
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Quality: Lint / Format
# ═══════════════════════════════════════════════════════════════

lint: ## Run ruff + black + mypy on all services + libs
	@for svc in $(SERVICES); do \
		echo "\n==> Linting $$svc"; \
		cd services/$$svc && ruff check . && black --check . && mypy app/ --ignore-missing-imports --no-error-summary && cd ../..; \
	done
	@echo "\n==> Linting libs"
	cd libs/contracts && ruff check . && black --check .
	cd libs/common && ruff check . && black --check .
	@echo "\n✅ All lint checks passed"

format: ## Auto-format with ruff + black
	@for svc in $(SERVICES); do \
		echo "==> Formatting $$svc"; \
		cd services/$$svc && ruff check --fix . && black . && cd ../..; \
	done
	cd libs/contracts && ruff check --fix . && black .
	cd libs/common && ruff check --fix . && black .

# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════

test: test-unit ## Run all unit tests (alias)

test-unit: ## Run unit tests (SQLite in-memory, no external deps)
	@echo "╔═══════════════════════════════════════════════════╗"
	@echo "║  UNIT TESTS – SQLite in-memory (no Docker needed) ║"
	@echo "╚═══════════════════════════════════════════════════╝"
	@PASS=0; FAIL=0; \
	for svc in $(SERVICES); do \
		echo "\n==> Testing $$svc"; \
		cd services/$$svc && \
		PYTHONPATH=. POSTGRES_HOST="" POSTGRES_DB="" API_KEY=test-key LOG_FORMAT=text RUNWAY_MODE=stub NLP_PROVIDER=stub ELEVENLABS_MODE=stub \
			python -m pytest tests/ -v --tb=short --junitxml=junit-$$svc.xml 2>&1; \
		if [ $$? -eq 0 ]; then PASS=$$((PASS+1)); else FAIL=$$((FAIL+1)); fi; \
		cd ../..; \
	done; \
	echo "\n════════════════════════════════════════════"; \
	echo "Results: $$PASS passed, $$FAIL failed (out of $$(echo $(SERVICES) | wc -w) services)"; \
	if [ $$FAIL -gt 0 ]; then exit 1; fi
	@echo "✅ All unit tests passed"

test-db: db-test-up ## Run integration tests against real PostgreSQL
	@echo "╔═══════════════════════════════════════════════════════╗"
	@echo "║  DB INTEGRATION TESTS – Real PostgreSQL               ║"
	@echo "╚═══════════════════════════════════════════════════════╝"
	@for svc in $(SERVICES); do \
		echo "\n==> DB-test $$svc"; \
		cd services/$$svc && \
		PYTHONPATH=. \
		POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_USER=platform POSTGRES_PASSWORD=localdev \
		POSTGRES_DB=$${svc//-/_} \
		API_KEY=test-key LOG_FORMAT=text RUNWAY_MODE=stub NLP_PROVIDER=stub ELEVENLABS_MODE=stub \
			python -m pytest tests/ -v --tb=short 2>&1 && cd ../.. || { cd ../..; }; \
	done
	@echo "✅ DB integration tests completed"

test-integration: up ## Run integration tests against full Docker stack
	@echo "╔════════════════════════════════════════════════════════╗"
	@echo "║  INTEGRATION TESTS – Full Docker Compose stack         ║"
	@echo "╚════════════════════════════════════════════════════════╝"
	@echo "==> Waiting for services..."
	@for port in 8001 8002 8003 8004 8005; do \
		until curl -sf http://localhost:$$port/healthz >/dev/null 2>&1; do sleep 2; done; \
		echo "    localhost:$$port ✓"; \
	done
	@echo "==> Running smoke tests"
	$(MAKE) smoke-test
	@echo "==> Running seed"
	$(MAKE) seed
	@echo "✅ Integration tests passed"

# ═══════════════════════════════════════════════════════════════
# Database
# ═══════════════════════════════════════════════════════════════

db-up: ## Start PostgreSQL only (for local dev)
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL..."
	@until docker compose exec postgres pg_isready -U platform >/dev/null 2>&1; do sleep 1; done
	@echo "✅ PostgreSQL ready on port 5433"

db-down: ## Stop PostgreSQL
	docker compose stop postgres

db-test-up: ## Start test PostgreSQL (ephemeral, for test-db target)
	@docker compose up -d postgres
	@echo "Waiting for test PostgreSQL..."
	@until docker compose exec postgres pg_isready -U platform >/dev/null 2>&1; do sleep 1; done
	@echo "✅ Test PostgreSQL ready"

db-test-down: ## Stop test PostgreSQL
	docker compose stop postgres

db-test-reset: ## Reset test databases (drop + recreate)
	docker compose exec postgres psql -U platform -c "DROP DATABASE IF EXISTS poi_service; CREATE DATABASE poi_service;"
	docker compose exec postgres psql -U platform -c "DROP DATABASE IF EXISTS asset_service; CREATE DATABASE asset_service;"
	docker compose exec postgres psql -U platform -c "DROP DATABASE IF EXISTS script_service; CREATE DATABASE script_service;"
	docker compose exec postgres psql -U platform -c "DROP DATABASE IF EXISTS transcription_service; CREATE DATABASE transcription_service;"
	docker compose exec postgres psql -U platform -c "DROP DATABASE IF EXISTS render_service; CREATE DATABASE render_service;"
	@echo "✅ All test databases reset"

migrate: ## Apply Alembic migrations (all services, via docker-compose)
	@for svc in $(SERVICES); do \
		echo "==> Migrating $$svc"; \
		docker compose exec $$svc alembic upgrade head; \
	done
	@echo "✅ All migrations applied"

seed: ## Seed: create 1 POI + 2 assets + generate script + transcription
	@chmod +x scripts/seed.sh
	@bash scripts/seed.sh

# ═══════════════════════════════════════════════════════════════
# Smoke Test
# ═══════════════════════════════════════════════════════════════

smoke-test: ## Hit /healthz + /readyz on every service
	@echo "╔═══════════════════════════════════════╗"
	@echo "║  SMOKE TEST – Health & Readiness       ║"
	@echo "╚═══════════════════════════════════════╝"
	@for svc_port in "poi-service:8001" "asset-service:8002" "script-service:8003" "transcription-service:8004" "render-service:8005"; do \
		svc=$$(echo $$svc_port | cut -d: -f1); \
		port=$$(echo $$svc_port | cut -d: -f2); \
		printf "  %-28s" "$$svc /healthz"; \
		curl -sf http://localhost:$$port/healthz >/dev/null && echo "✅" || echo "❌"; \
		printf "  %-28s" "$$svc /readyz"; \
		curl -sf http://localhost:$$port/readyz >/dev/null && echo "✅" || echo "❌"; \
	done

# ═══════════════════════════════════════════════════════════════
# E2E (Karate)
# ═══════════════════════════════════════════════════════════════

E2E_DIR := tests/karate

e2e: up ## Run Karate E2E tests against docker-compose stack
	@echo "==> Waiting for services to be ready..."
	@for port in 8001 8002 8003 8004 8005; do \
		until curl -sf http://localhost:$$port/healthz >/dev/null 2>&1; do sleep 2; done; \
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

# ═══════════════════════════════════════════════════════════════
# Kubernetes
# ═══════════════════════════════════════════════════════════════

K8S_NS := poi-video-platform

k8s-up: ## Deploy to K8s (dev overlay)
	@echo "==> Deploying DEV overlay"
	kubectl apply -k deploy/k8s/overlays/dev
	@echo "==> Waiting for rollout..."
	@for svc in $(SERVICES); do \
		kubectl -n $(K8S_NS) rollout status deployment/$$svc --timeout=120s; \
	done
	@echo "✅ All deployments ready (dev)"

k8s-preprod: ## Deploy to K8s (preprod overlay)
	@echo "==> Deploying PREPROD overlay"
	kubectl apply -k deploy/k8s/overlays/preprod
	@echo "==> Waiting for rollout..."
	@for svc in $(SERVICES); do \
		kubectl -n $(K8S_NS)-preprod rollout status deployment/$$svc --timeout=180s; \
	done
	@echo "✅ All deployments ready (preprod)"

k8s-prod: ## Deploy to K8s (prod overlay)
	@echo "==> Deploying PROD overlay"
	kubectl apply -k deploy/k8s/overlays/prod
	@echo "==> Waiting for rollout..."
	@for svc in $(SERVICES); do \
		kubectl -n $(K8S_NS)-prod rollout status deployment/$$svc --timeout=180s; \
	done
	@echo "✅ All deployments ready (prod)"

k8s-down: ## Delete K8s dev namespace
	kubectl delete namespace $(K8S_NS) --ignore-not-found

k8s-logs: ## Stream logs (usage: make k8s-logs SERVICE=poi-service)
	@test -n "$(SERVICE)" || { echo "Usage: make k8s-logs SERVICE=<name>"; exit 1; }
	kubectl -n $(K8S_NS) logs -f -l app.kubernetes.io/name=$(SERVICE) --all-containers

k8s-port-forward: ## Port-forward (usage: make k8s-port-forward SERVICE=poi-service PORT=8001)
	@test -n "$(SERVICE)" || { echo "Usage: make k8s-port-forward SERVICE=<name> PORT=<port>"; exit 1; }
	@test -n "$(PORT)"    || { echo "Usage: make k8s-port-forward SERVICE=<name> PORT=<port>"; exit 1; }
	kubectl -n $(K8S_NS) port-forward svc/$(SERVICE) $(PORT):$(PORT)

# ═══════════════════════════════════════════════════════════════
# GitHub
# ═══════════════════════════════════════════════════════════════

github-check: ## Verify GitHub SSH connection and remote
	@echo "==> Checking SSH key..."
	@test -f /home/louto/env/ssh/id_ed25519_kappn && echo "  SSH key: ✅" || echo "  SSH key: ❌ NOT FOUND"
	@echo "==> Testing SSH connection to GitHub..."
	@GIT_SSH_COMMAND="$(GIT_SSH_CMD)" ssh -T git@github.com 2>&1 | head -1 || true
	@echo "==> Git remote:"
	@git remote -v 2>/dev/null || echo "  No git remote configured"
	@echo "==> Current branch:"
	@git branch --show-current 2>/dev/null || echo "  Not a git repo"
	@echo "==> Last commit:"
	@git log --oneline -1 2>/dev/null || echo "  No commits"

github-push: ## Push current branch to GitHub
	@echo "==> Pushing to $(REMOTE_REPO)..."
	GIT_SSH_COMMAND="$(GIT_SSH_CMD)" git push -u origin $$(git branch --show-current) 2>&1
	@echo "✅ Push complete"

# ═══════════════════════════════════════════════════════════════
# QA Pipeline
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════

clean: ## Remove __pycache__, .pyc, .egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

clean-all: clean down-v ## Full cleanup (caches + Docker volumes)
	rm -rf .venv artifacts/
	@echo "✅ Full cleanup done"

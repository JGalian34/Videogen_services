# ── Build stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY libs/contracts /tmp/contracts
COPY libs/common /tmp/common
RUN pip install --no-cache-dir --prefix=/install /tmp/contracts /tmp/common \
    && rm -rf /tmp/contracts /tmp/common

COPY services/asset-service/pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ──────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /install /usr/local

WORKDIR /app
ENV PYTHONPATH=/app

COPY services/asset-service/app /app/app
COPY services/asset-service/alembic.ini /app/alembic.ini
COPY services/asset-service/alembic /app/alembic

RUN mkdir -p /data/assets && chown app:app /data/assets

USER app

EXPOSE 8002
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8002 --log-level info"]

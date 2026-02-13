"""Render-service – FastAPI application entry-point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.renders import router as renders_router
from app.core.logging import init_logging
from app.db.session import SessionLocal
from common.errors import register_error_handlers
from common.kafka import start_kafka_producer, stop_kafka_producer
from common.middleware import APIKeyMiddleware, CorrelationMiddleware, RequestSizeLimitMiddleware

init_logging()

_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Kafka producer + consumer on startup, cancel on shutdown."""
    global _consumer_task
    await start_kafka_producer()
    try:
        from app.integrations.kafka_consumer import start_consumer

        _consumer_task = asyncio.create_task(start_consumer(SessionLocal))
    except Exception:
        pass  # Kafka may not be available in tests
    yield
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    await stop_kafka_producer()


app = FastAPI(
    title="Render Service",
    description="Scene-by-scene video rendering (Runway stub/live)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(CorrelationMiddleware)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(renders_router)

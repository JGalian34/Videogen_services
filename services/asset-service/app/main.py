"""Asset-service – FastAPI application entry-point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.assets import router as assets_router
from app.core.logging import init_logging
from common.errors import register_error_handlers
from common.kafka import start_kafka_producer, stop_kafka_producer
from common.middleware import APIKeyMiddleware, CorrelationMiddleware, RequestSizeLimitMiddleware

init_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_kafka_producer()
    yield
    await stop_kafka_producer()


app = FastAPI(
    title="Asset Service",
    description="Manage assets linked to POIs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(CorrelationMiddleware)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(assets_router)

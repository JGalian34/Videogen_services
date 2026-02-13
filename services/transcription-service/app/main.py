"""Transcription-service – FastAPI application entry-point.

Handles both:
  - STT (speech-to-text): /transcriptions/*
  - TTS (text-to-speech / voiceover): /voiceovers/*
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.transcriptions import router as transcriptions_router
from app.api.routers.voiceovers import router as voiceovers_router
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
    title="Transcription & Voiceover Service",
    description="STT transcription + TTS voiceover generation (ElevenLabs)",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(CorrelationMiddleware)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(transcriptions_router)
app.include_router(voiceovers_router)

"""Kafka / Redpanda producer for transcription-service events.

Handles both STT (transcription.completed) and TTS (voiceover.completed) events.
Uses the shared ``publish_event`` helper from ``common.kafka``.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.events import VideoEventType

from app.core.config import KAFKA_TOPIC
from common.kafka import publish_event

logger = logging.getLogger(__name__)


async def publish_video_event(event_type: str, job: Any) -> None:
    """Publish a domain event to the ``video.events`` topic.

    Handles both Transcription and Voiceover models.
    """
    # Build payload based on event type
    if event_type == VideoEventType.VOICEOVER_COMPLETED:
        payload = {
            "voiceover_id": str(job.id),
            "poi_id": str(job.poi_id),
            "script_id": str(job.script_id),
            "status": job.status,
            "full_audio_path": job.full_audio_path,
            "total_duration_seconds": job.total_duration_seconds,
            "scene_audios": job.scene_audios,
            "provider": job.provider,
            "voice_id": job.voice_id,
        }
    else:
        # Transcription events
        payload = {
            "transcription_id": str(job.id),
            "poi_id": str(job.poi_id),
            "asset_video_id": str(job.asset_video_id),
            "status": job.status,
        }

    await publish_event(
        topic=KAFKA_TOPIC,
        event_type=event_type,
        payload=payload,
        key=str(job.poi_id),
    )
    logger.info("Event published: %s for %s", event_type, job.id)

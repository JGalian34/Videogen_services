"""Kafka / Redpanda producer for script-service events.

Uses the shared ``publish_event`` helper from ``common.kafka``
which serialises via ``DomainEvent`` from ``contracts``.
"""

from __future__ import annotations

import logging

from app.core.config import KAFKA_TOPIC
from common.kafka import publish_event

logger = logging.getLogger(__name__)


async def publish_video_event(event_type: str, script) -> None:
    """Publish a domain event to the ``video.events`` topic.

    The payload includes the full scene list and narration text so
    downstream consumers (render-service, voiceover) can work without
    an extra HTTP round-trip.
    """
    await publish_event(
        topic=KAFKA_TOPIC,
        event_type=event_type,
        payload={
            "script_id": str(script.id),
            "poi_id": str(script.poi_id),
            "title": script.title,
            "tone": script.tone,
            "scene_count": len(script.scenes) if script.scenes else 0,
            "total_duration_seconds": script.total_duration_seconds,
            "scenes": script.scenes or [],
            "narration_text": script.narration_text or "",
        },
        key=str(script.poi_id),
    )
    logger.info("Event published: %s for script %s", event_type, script.id)

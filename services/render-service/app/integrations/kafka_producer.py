"""Kafka / Redpanda producer for render-service events.

Uses the shared ``publish_event`` helper from ``common.kafka``
which serialises via ``DomainEvent`` from ``contracts``.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import KAFKA_TOPIC
from common.kafka import publish_event

logger = logging.getLogger(__name__)


async def publish_video_event(event_type: str, payload: dict) -> None:
    """Publish a domain event to the ``video.events`` topic."""
    key = payload.get("poi_id", str(uuid.uuid4()))
    await publish_event(
        topic=KAFKA_TOPIC,
        event_type=event_type,
        payload=payload,
        key=key,
    )
    logger.info("Event published: %s", event_type)

"""Kafka / Redpanda producer for poi-service events.

Uses the shared ``publish_event`` helper from ``common.kafka``
which serialises via ``DomainEvent`` from ``contracts``.
"""

from __future__ import annotations

import logging

from app.core.config import KAFKA_TOPIC
from common.kafka import publish_event

logger = logging.getLogger(__name__)


def _poi_snapshot(poi) -> dict:
    return {
        "id": str(poi.id),
        "name": poi.name,
        "description": poi.description,
        "address": poi.address,
        "lat": poi.lat,
        "lon": poi.lon,
        "poi_type": poi.poi_type,
        "tags": poi.tags or [],
        "status": poi.status,
        "version": poi.version,
    }


async def publish_poi_event(event_type: str, poi) -> None:
    """Publish a domain event to the ``poi.events`` topic."""
    await publish_event(
        topic=KAFKA_TOPIC,
        event_type=event_type,
        payload=_poi_snapshot(poi),
        key=str(poi.id),
    )
    logger.info("Event published: %s for POI %s", event_type, poi.id)

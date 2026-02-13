"""Kafka / Redpanda producer for asset-service events.

Uses the shared ``publish_event`` helper from ``common.kafka``
which serialises via ``DomainEvent`` from ``contracts``.
"""

from __future__ import annotations

import logging

from app.core.config import KAFKA_TOPIC
from common.kafka import publish_event

logger = logging.getLogger(__name__)


async def publish_asset_event(event_type: str, asset) -> None:
    """Publish a domain event to the ``asset.events`` topic."""
    await publish_event(
        topic=KAFKA_TOPIC,
        event_type=event_type,
        payload={
            "id": str(asset.id),
            "poi_id": str(asset.poi_id),
            "name": asset.name,
            "asset_type": asset.asset_type,
            "file_path": asset.file_path,
            "version": asset.version,
        },
        key=str(asset.id),
    )
    logger.info("Event published: %s for asset %s", event_type, asset.id)

"""Shared event contracts – versioned Pydantic schemas for Kafka / Redpanda topics."""

from contracts.events import (
    AssetEventType,
    DomainEvent,
    POIEventType,
    VideoEventType,
)

__all__ = [
    "DomainEvent",
    "POIEventType",
    "AssetEventType",
    "VideoEventType",
]

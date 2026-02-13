"""
Versioned event envelope used across all services.

Every event published on Redpanda MUST use :class:`DomainEvent` as its
envelope so consumers can deserialise uniformly.

Topics:
  - poi.events
  - asset.events
  - video.events
  - dlq.events
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# ── Event types ────────────────────────────────────────────────────────


class POIEventType(str, enum.Enum):
    POI_CREATED = "poi.created"
    POI_UPDATED = "poi.updated"
    POI_STATUS_CHANGED = "poi.status_changed"
    POI_VALIDATED = "poi.validated"
    POI_PUBLISHED = "poi.published"
    POI_ARCHIVED = "poi.archived"


class AssetEventType(str, enum.Enum):
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"


class VideoEventType(str, enum.Enum):
    SCRIPT_GENERATED = "script.generated"
    TRANSCRIPTION_COMPLETED = "transcription.completed"
    VOICEOVER_COMPLETED = "voiceover.completed"
    RENDER_SCENE_GENERATED = "render.scene.generated"
    RENDER_COMPLETED = "render.completed"
    VIDEO_PUBLISHED = "video.published"


# ── Envelope ───────────────────────────────────────────────────────────


class DomainEvent(BaseModel):
    """Stable event envelope published on any Redpanda topic."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = 1
    correlation_id: str = ""
    payload: dict[str, Any] = {}

    def to_kafka_value(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_kafka_value(cls, raw: bytes) -> "DomainEvent":
        return cls.model_validate_json(raw)

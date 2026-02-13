"""Pydantic schemas for script-service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SceneSchema(BaseModel):
    scene_number: int
    title: str
    description: str
    duration_seconds: float
    asset_id: str | None = None
    visual_prompt: str = ""


class ScriptResponse(BaseModel):
    id: uuid.UUID
    poi_id: uuid.UUID
    title: str
    tone: str
    total_duration_seconds: float
    scenes: list[dict[str, Any]]
    narration_text: str | None
    nlp_provider: str
    metadata: dict[str, Any]
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "ScriptResponse":
        return cls(
            id=obj.id,
            poi_id=obj.poi_id,
            title=obj.title,
            tone=obj.tone,
            total_duration_seconds=obj.total_duration_seconds,
            scenes=obj.scenes or [],
            narration_text=obj.narration_text,
            nlp_provider=obj.nlp_provider,
            metadata=obj.metadata_ or {},
            version=obj.version,
            created_at=obj.created_at,
        )


class ScriptListResponse(BaseModel):
    items: list[ScriptResponse]
    total: int
    page: int = 1
    page_size: int = 20


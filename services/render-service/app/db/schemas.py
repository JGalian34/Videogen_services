"""Pydantic schemas for render-service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RenderSceneResponse(BaseModel):
    id: uuid.UUID
    scene_number: int
    title: str
    visual_prompt: str | None
    status: str
    output_path: str | None
    duration_seconds: float
    provider: str
    cost: float

    model_config = {"from_attributes": True}


class RenderJobResponse(BaseModel):
    id: uuid.UUID
    poi_id: uuid.UUID
    script_id: uuid.UUID
    status: str
    total_scenes: int
    completed_scenes: int
    output_path: str | None
    voiceover_audio_path: str | None = None
    voiceover_id: str | None = None
    published_url: str | None = None
    published_at: datetime | None = None
    error_message: str | None
    metadata: dict[str, Any]
    scenes: list[RenderSceneResponse]
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "RenderJobResponse":
        return cls(
            id=obj.id,
            poi_id=obj.poi_id,
            script_id=obj.script_id,
            status=obj.status,
            total_scenes=obj.total_scenes,
            completed_scenes=obj.completed_scenes,
            output_path=obj.output_path,
            voiceover_audio_path=obj.voiceover_audio_path,
            voiceover_id=obj.voiceover_id,
            published_url=obj.published_url,
            published_at=obj.published_at,
            error_message=obj.error_message,
            metadata=obj.metadata_ or {},
            scenes=[RenderSceneResponse.model_validate(s) for s in (obj.scenes or [])],
            created_at=obj.created_at,
            completed_at=obj.completed_at,
        )


class RenderListResponse(BaseModel):
    items: list[RenderJobResponse]
    total: int
    page: int = 1
    page_size: int = 20


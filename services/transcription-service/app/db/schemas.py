"""Pydantic schemas for transcription-service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    id: uuid.UUID
    poi_id: uuid.UUID
    asset_video_id: uuid.UUID
    status: str
    language: str
    text: str | None
    confidence: float | None
    duration_seconds: float | None
    segments: list | None
    error_message: str | None
    metadata: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "TranscriptionResponse":
        return cls(
            id=obj.id,
            poi_id=obj.poi_id,
            asset_video_id=obj.asset_video_id,
            status=obj.status,
            language=obj.language,
            text=obj.text,
            confidence=obj.confidence,
            duration_seconds=obj.duration_seconds,
            segments=obj.segments,
            error_message=obj.error_message,
            metadata=obj.metadata_ or {},
            created_at=obj.created_at,
            completed_at=obj.completed_at,
        )


class TranscriptionListResponse(BaseModel):
    items: list[TranscriptionResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ── Voiceover (TTS) ────────────────────────────────────────────

class VoiceoverRequest(BaseModel):
    poi_id: uuid.UUID
    script_id: uuid.UUID
    narration_text: str
    scenes: list[dict[str, Any]] = []
    language: str = "fr"
    voice_id: str | None = None


class SceneAudioSchema(BaseModel):
    scene_number: int
    audio_path: str
    duration_seconds: float
    text: str


class VoiceoverResponse(BaseModel):
    id: uuid.UUID
    poi_id: uuid.UUID
    script_id: uuid.UUID
    status: str
    language: str
    voice_id: str | None
    provider: str
    full_audio_path: str | None
    full_narration_text: str | None
    total_duration_seconds: float | None
    scene_audios: list | None
    cost: float
    error_message: str | None
    metadata: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "VoiceoverResponse":
        return cls(
            id=obj.id,
            poi_id=obj.poi_id,
            script_id=obj.script_id,
            status=obj.status,
            language=obj.language,
            voice_id=obj.voice_id,
            provider=obj.provider,
            full_audio_path=obj.full_audio_path,
            full_narration_text=obj.full_narration_text,
            total_duration_seconds=obj.total_duration_seconds,
            scene_audios=obj.scene_audios,
            cost=obj.cost,
            error_message=obj.error_message,
            metadata=obj.metadata_ or {},
            created_at=obj.created_at,
            completed_at=obj.completed_at,
        )


class VoiceoverListResponse(BaseModel):
    items: list[VoiceoverResponse]
    total: int


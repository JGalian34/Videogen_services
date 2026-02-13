"""SQLAlchemy models for transcription-service."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text, Float, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    poi_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    asset_video_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TranscriptionStatus.PENDING.value, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="fr", nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Voiceover(Base):
    """TTS voiceover generated from a script's narration text (ElevenLabs)."""

    __tablename__ = "voiceovers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    poi_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TranscriptionStatus.PENDING.value, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="fr", nullable=False)
    voice_id: Mapped[str] = mapped_column(String(100), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="stub", nullable=False)

    # Full narration audio
    full_audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    full_narration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Per-scene audio breakdown (JSON array)
    scene_audios: Mapped[list | None] = mapped_column(JSON, nullable=True)

    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

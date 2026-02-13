"""SQLAlchemy models for render-service."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RenderStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    poi_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    script_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RenderStatus.PENDING.value, nullable=False)
    total_scenes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_scenes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    voiceover_audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    voiceover_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    published_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scenes: Mapped[list["RenderScene"]] = relationship("RenderScene", back_populates="render_job", lazy="selectin")


class RenderScene(Base):
    __tablename__ = "render_scenes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    render_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("render_jobs.id", ondelete="CASCADE"), nullable=False
    )
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=RenderStatus.PENDING.value, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="stub", nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    render_job: Mapped["RenderJob"] = relationship("RenderJob", back_populates="scenes")

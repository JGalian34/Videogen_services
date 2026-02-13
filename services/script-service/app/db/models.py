"""SQLAlchemy models for script-service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text, Float, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoScript(Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    poi_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tone: Mapped[str] = mapped_column(String(50), default="warm", nullable=False)
    total_duration_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    scenes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    narration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    nlp_provider: Mapped[str] = mapped_column(String(50), default="stub", nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

"""
Transcription business-logic layer.

Implements a stub pipeline: job created → worker → result stored.
In production, the 'worker' step would call a real STT model (Whisper, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from contracts.events import VideoEventType

from app.db.models import Transcription, TranscriptionStatus
from app.integrations.kafka_producer import publish_video_event
from common.errors import NotFoundError

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, db: Session):
        self.db = db

    async def start_transcription(self, poi_id: uuid.UUID, asset_video_id: uuid.UUID) -> Transcription:
        """Create a transcription job and run the stub worker."""
        job = Transcription(
            poi_id=poi_id,
            asset_video_id=asset_video_id,
            status=TranscriptionStatus.PENDING.value,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info("Transcription job created: %s", job.id)

        # Run stub worker (simulates async processing)
        await self._stub_worker(job)
        return job

    async def _stub_worker(self, job: Transcription) -> None:
        """Stub worker that generates a placeholder transcription."""
        job.status = TranscriptionStatus.PROCESSING.value
        self.db.commit()

        # Simulate processing delay
        await asyncio.sleep(0.1)

        job.status = TranscriptionStatus.COMPLETED.value
        job.text = (
            "Bienvenue dans cette visite virtuelle. "
            "Ce bien d'exception offre des prestations haut de gamme "
            "dans un cadre de vie idéal. "
            "Les espaces de vie sont lumineux et spacieux."
        )
        job.confidence = 0.95
        job.duration_seconds = 12.5
        job.segments = [
            {"start": 0.0, "end": 3.0, "text": "Bienvenue dans cette visite virtuelle."},
            {
                "start": 3.0,
                "end": 7.5,
                "text": "Ce bien d'exception offre des prestations haut de gamme dans un cadre de vie idéal.",
            },
            {"start": 7.5, "end": 12.5, "text": "Les espaces de vie sont lumineux et spacieux."},
        ]
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)

        await publish_video_event(VideoEventType.TRANSCRIPTION_COMPLETED, job)
        logger.info("Transcription completed: %s", job.id)

    def get_transcription(self, transcription_id: uuid.UUID) -> Transcription:
        job = self.db.get(Transcription, transcription_id)
        if not job:
            raise NotFoundError(f"Transcription {transcription_id} not found")
        return job

    def list_transcriptions(
        self, *, poi_id: uuid.UUID | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[Transcription], int]:
        q = self.db.query(Transcription)
        if poi_id:
            q = q.filter(Transcription.poi_id == poi_id)
        total = q.count()
        items = q.order_by(Transcription.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

"""
Voiceover (TTS) business-logic layer.

Generates voice narration from a script using ElevenLabs (stub or live).
Produces per-scene audio segments + a full narration track.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from contracts.events import VideoEventType

from app.db.models import TranscriptionStatus, Voiceover
from app.db.schemas import VoiceoverRequest
from app.integrations.elevenlabs_client import get_tts_client
from app.integrations.kafka_producer import publish_video_event
from common.errors import NotFoundError

logger = logging.getLogger(__name__)


class VoiceoverService:
    def __init__(self, db: Session):
        self.db = db

    async def generate_voiceover(self, request: VoiceoverRequest) -> Voiceover:
        """Generate TTS voiceover for a script's narration text."""
        # 1) Create pending record
        voiceover = Voiceover(
            poi_id=request.poi_id,
            script_id=request.script_id,
            status=TranscriptionStatus.PENDING.value,
            language=request.language,
            voice_id=request.voice_id,
            full_narration_text=request.narration_text,
        )
        self.db.add(voiceover)
        self.db.commit()
        self.db.refresh(voiceover)

        logger.info("Voiceover job created: %s for script %s", voiceover.id, request.script_id)

        # 2) Process TTS
        await self._process_tts(voiceover, request)
        return voiceover

    async def _process_tts(self, voiceover: Voiceover, request: VoiceoverRequest) -> None:
        """Run TTS generation (stub or ElevenLabs)."""
        voiceover.status = TranscriptionStatus.PROCESSING.value
        self.db.commit()

        try:
            client = get_tts_client()

            if request.scenes:
                # Multi-scene: generate per-scene audio + full narration
                result = await client.generate_multi_scene_speech(
                    scenes=request.scenes,
                    narration_text=request.narration_text,
                    voice_id=request.voice_id,
                    language=request.language,
                )
                voiceover.full_audio_path = result["full_audio_path"]
                voiceover.scene_audios = result["scene_audios"]
                voiceover.total_duration_seconds = result["total_duration_seconds"]
                voiceover.provider = result["provider"]
                voiceover.voice_id = result["voice_id"]
                voiceover.cost = result["cost"]
            else:
                # Single narration
                result = await client.generate_speech(
                    text=request.narration_text,
                    voice_id=request.voice_id,
                    language=request.language,
                )
                voiceover.full_audio_path = result["audio_path"]
                voiceover.total_duration_seconds = result["duration_seconds"]
                voiceover.provider = result["provider"]
                voiceover.voice_id = result["voice_id"]
                voiceover.cost = result["cost"]

            voiceover.status = TranscriptionStatus.COMPLETED.value
            voiceover.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(voiceover)

            # Publish event
            await publish_video_event(VideoEventType.VOICEOVER_COMPLETED, voiceover)
            logger.info("Voiceover completed: %s (%.1fs, provider=%s)",
                        voiceover.id, voiceover.total_duration_seconds or 0, voiceover.provider)

        except Exception as exc:
            voiceover.status = TranscriptionStatus.FAILED.value
            voiceover.error_message = str(exc)
            self.db.commit()
            logger.error("Voiceover failed: %s – %s", voiceover.id, exc, exc_info=True)
            raise

    def get_voiceover(self, voiceover_id: uuid.UUID) -> Voiceover:
        obj = self.db.get(Voiceover, voiceover_id)
        if not obj:
            raise NotFoundError(f"Voiceover {voiceover_id} not found")
        return obj

    def list_voiceovers(self, *, poi_id: uuid.UUID | None = None, script_id: uuid.UUID | None = None) -> tuple[list[Voiceover], int]:
        q = self.db.query(Voiceover)
        if poi_id:
            q = q.filter(Voiceover.poi_id == poi_id)
        if script_id:
            q = q.filter(Voiceover.script_id == script_id)
        items = q.order_by(Voiceover.created_at.desc()).all()
        return items, len(items)


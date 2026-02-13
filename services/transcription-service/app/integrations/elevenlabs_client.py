"""
ElevenLabs Text-to-Speech client.

Supports two modes:
  - ``stub`` (default): no external API calls, returns placeholder audio metadata
  - ``live``: calls the real ElevenLabs API (requires ELEVENLABS_API_KEY env var)

Switch via ELEVENLABS_MODE environment variable.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import logging
import os
import uuid
from typing import Any

from app.core.config import ELEVENLABS_API_KEY, ELEVENLABS_MODE, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)


class TTSClient(abc.ABC):
    """Base TTS client interface."""

    @abc.abstractmethod
    async def generate_speech(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        """Generate speech audio from text.

        Returns dict with:
          - audio_path: str (local file path)
          - duration_seconds: float
          - provider: str
          - voice_id: str
          - cost: float
        """
        ...

    @abc.abstractmethod
    async def generate_multi_scene_speech(
        self,
        scenes: list[dict[str, Any]],
        narration_text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        """Generate per-scene audio + full narration.

        Returns dict with:
          - full_audio_path: str
          - scene_audios: list[dict] (each with audio_path, scene_number, duration_seconds)
          - total_duration_seconds: float
          - provider: str
          - cost: float
        """
        ...


class StubTTSClient(TTSClient):
    """Returns placeholder data without making any API call."""

    async def generate_speech(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        await asyncio.sleep(0.05)  # Simulate processing
        file_id = hashlib.md5(text.encode()).hexdigest()[:12]
        # Estimate duration: ~150 words/minute in French
        word_count = len(text.split())
        duration = max(2.0, word_count / 2.5)  # ~2.5 words/second
        audio_path = f"/data/audio/voiceover_{file_id}.mp3"

        return {
            "audio_path": audio_path,
            "duration_seconds": round(duration, 1),
            "provider": "stub",
            "voice_id": voice_id or "stub-fr-male-01",
            "cost": 0.0,
            "language": language,
            "character_count": len(text),
        }

    async def generate_multi_scene_speech(
        self,
        scenes: list[dict[str, Any]],
        narration_text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        await asyncio.sleep(0.1)  # Simulate processing

        scene_audios = []
        total_duration = 0.0
        total_cost = 0.0

        # Generate per-scene narration segments
        # Split narration proportionally across scenes
        sentences = [s.strip() for s in narration_text.split(".") if s.strip()]
        scenes_count = len(scenes) or 1

        for i, scene in enumerate(scenes):
            # Assign narration sentences to scenes proportionally
            start_idx = int(i * len(sentences) / scenes_count)
            end_idx = int((i + 1) * len(sentences) / scenes_count)
            scene_text = ". ".join(sentences[start_idx:end_idx]) + "." if start_idx < len(sentences) else ""

            if not scene_text.strip().rstrip("."):
                scene_text = scene.get("description", f"Scene {i + 1}")

            result = await self.generate_speech(scene_text, voice_id=voice_id, language=language)
            scene_audios.append(
                {
                    "scene_number": scene.get("scene_number", i + 1),
                    "audio_path": result["audio_path"],
                    "duration_seconds": result["duration_seconds"],
                    "text": scene_text,
                }
            )
            total_duration += result["duration_seconds"]
            total_cost += result["cost"]

        # Generate full narration audio
        full_result = await self.generate_speech(narration_text, voice_id=voice_id, language=language)

        return {
            "full_audio_path": full_result["audio_path"],
            "scene_audios": scene_audios,
            "total_duration_seconds": round(total_duration, 1),
            "full_narration_duration_seconds": full_result["duration_seconds"],
            "provider": "stub",
            "voice_id": voice_id or "stub-fr-male-01",
            "cost": round(total_cost, 4),
            "language": language,
        }


class LiveElevenLabsClient(TTSClient):
    """Calls the real ElevenLabs API."""

    def __init__(self, api_key: str, voice_id: str):
        self.api_key = api_key
        self.default_voice_id = voice_id

    async def generate_speech(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        if not self.api_key:
            logger.error("ELEVENLABS_API_KEY not set – falling back to stub")
            return await StubTTSClient().generate_speech(text, voice_id=voice_id, language=language)

        vid = voice_id or self.default_voice_id
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                    headers={
                        "xi-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                        },
                    },
                )
                resp.raise_for_status()

                # Save audio file
                file_id = str(uuid.uuid4())[:12]
                audio_dir = "/data/audio"
                os.makedirs(audio_dir, exist_ok=True)
                audio_path = f"{audio_dir}/voiceover_{file_id}.mp3"
                with open(audio_path, "wb") as f:
                    f.write(resp.content)

                # Estimate duration from file size (~16kbps for mp3)
                duration = len(resp.content) / (16 * 1024 / 8)

                return {
                    "audio_path": audio_path,
                    "duration_seconds": round(duration, 1),
                    "provider": "elevenlabs",
                    "voice_id": vid,
                    "cost": len(text) * 0.00003,  # ~$0.03 per 1000 chars
                    "language": language,
                    "character_count": len(text),
                }
        except Exception as exc:
            logger.error("ElevenLabs API error: %s – falling back to stub", exc)
            return await StubTTSClient().generate_speech(text, voice_id=voice_id, language=language)

    async def generate_multi_scene_speech(
        self,
        scenes: list[dict[str, Any]],
        narration_text: str,
        *,
        voice_id: str | None = None,
        language: str = "fr",
    ) -> dict[str, Any]:
        scene_audios = []
        total_duration = 0.0
        total_cost = 0.0

        sentences = [s.strip() for s in narration_text.split(".") if s.strip()]
        scenes_count = len(scenes) or 1

        for i, scene in enumerate(scenes):
            start_idx = int(i * len(sentences) / scenes_count)
            end_idx = int((i + 1) * len(sentences) / scenes_count)
            scene_text = ". ".join(sentences[start_idx:end_idx]) + "." if start_idx < len(sentences) else ""

            if not scene_text.strip().rstrip("."):
                scene_text = scene.get("description", f"Scene {i + 1}")

            result = await self.generate_speech(scene_text, voice_id=voice_id, language=language)
            scene_audios.append(
                {
                    "scene_number": scene.get("scene_number", i + 1),
                    "audio_path": result["audio_path"],
                    "duration_seconds": result["duration_seconds"],
                    "text": scene_text,
                }
            )
            total_duration += result["duration_seconds"]
            total_cost += result["cost"]

        full_result = await self.generate_speech(narration_text, voice_id=voice_id, language=language)

        return {
            "full_audio_path": full_result["audio_path"],
            "scene_audios": scene_audios,
            "total_duration_seconds": round(total_duration, 1),
            "full_narration_duration_seconds": full_result["duration_seconds"],
            "provider": "elevenlabs",
            "voice_id": voice_id or self.default_voice_id,
            "cost": round(total_cost + full_result["cost"], 4),
            "language": language,
        }


def get_tts_client() -> TTSClient:
    """Factory: returns the configured TTS client."""
    if ELEVENLABS_MODE == "live":
        return LiveElevenLabsClient(api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE_ID)
    return StubTTSClient()

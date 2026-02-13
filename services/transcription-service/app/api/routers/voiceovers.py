"""Voiceover (TTS) endpoints – ElevenLabs integration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import VoiceoverListResponse, VoiceoverRequest, VoiceoverResponse
from app.db.session import get_db
from app.services.voiceover_service import VoiceoverService

router = APIRouter(prefix="/voiceovers", tags=["voiceovers"])


def _svc(db: Session = Depends(get_db)) -> VoiceoverService:
    return VoiceoverService(db)


@router.post("/generate", response_model=VoiceoverResponse, status_code=201)
async def generate_voiceover(body: VoiceoverRequest, svc: VoiceoverService = Depends(_svc)):
    """Generate a TTS voiceover from a script's narration text.

    Supports multi-scene: if ``scenes`` is provided, generates per-scene
    audio segments + a full narration track.
    """
    voiceover = await svc.generate_voiceover(body)
    return VoiceoverResponse.from_model(voiceover)


@router.get("", response_model=VoiceoverListResponse)
async def list_voiceovers(
    poi_id: uuid.UUID | None = Query(None),
    script_id: uuid.UUID | None = Query(None),
    svc: VoiceoverService = Depends(_svc),
):
    items, total = svc.list_voiceovers(poi_id=poi_id, script_id=script_id)
    return VoiceoverListResponse(items=[VoiceoverResponse.from_model(v) for v in items], total=total)


@router.get("/{voiceover_id}", response_model=VoiceoverResponse)
async def get_voiceover(voiceover_id: uuid.UUID, svc: VoiceoverService = Depends(_svc)):
    return VoiceoverResponse.from_model(svc.get_voiceover(voiceover_id))

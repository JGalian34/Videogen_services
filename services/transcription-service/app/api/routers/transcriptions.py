"""Transcription endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import TranscriptionListResponse, TranscriptionResponse
from app.db.session import get_db
from app.services.transcription_service import TranscriptionService

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


def _svc(db: Session = Depends(get_db)) -> TranscriptionService:
    return TranscriptionService(db)


@router.post("/start", response_model=TranscriptionResponse, status_code=201)
async def start_transcription(
    poi_id: uuid.UUID = Query(...),
    asset_video_id: uuid.UUID = Query(...),
    svc: TranscriptionService = Depends(_svc),
):
    job = await svc.start_transcription(poi_id, asset_video_id)
    return TranscriptionResponse.from_model(job)


@router.get("", response_model=TranscriptionListResponse)
async def list_transcriptions(
    poi_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: TranscriptionService = Depends(_svc),
):
    items, total = svc.list_transcriptions(poi_id=poi_id, page=page, page_size=page_size)
    return TranscriptionListResponse(
        items=[TranscriptionResponse.from_model(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{transcription_id}", response_model=TranscriptionResponse)
async def get_transcription(transcription_id: uuid.UUID, svc: TranscriptionService = Depends(_svc)):
    return TranscriptionResponse.from_model(svc.get_transcription(transcription_id))

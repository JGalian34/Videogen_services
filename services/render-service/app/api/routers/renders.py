"""Render job endpoints – rendering, voiceover attachment, and video publication."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.schemas import RenderJobResponse, RenderListResponse
from app.db.session import get_db
from app.services.render_service import RenderService

router = APIRouter(prefix="/renders", tags=["renders"])


class AttachVoiceoverRequest(BaseModel):
    voiceover_id: str
    audio_path: str


def _svc(db: Session = Depends(get_db)) -> RenderService:
    return RenderService(db)


@router.get("", response_model=RenderListResponse)
async def list_renders(
    poi_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: RenderService = Depends(_svc),
):
    items, total = svc.list_renders(poi_id=poi_id, page=page, page_size=page_size)
    return RenderListResponse(items=[RenderJobResponse.from_model(r) for r in items], total=total, page=page, page_size=page_size)


@router.get("/{render_id}", response_model=RenderJobResponse)
async def get_render(render_id: uuid.UUID, svc: RenderService = Depends(_svc)):
    return RenderJobResponse.from_model(svc.get_render(render_id))


@router.post("/retry/{render_id}", response_model=RenderJobResponse)
async def retry_render(render_id: uuid.UUID, svc: RenderService = Depends(_svc)):
    job = await svc.retry_render(render_id)
    return RenderJobResponse.from_model(job)


@router.post("/{render_id}/voiceover", response_model=RenderJobResponse)
async def attach_voiceover(
    render_id: uuid.UUID,
    body: AttachVoiceoverRequest,
    svc: RenderService = Depends(_svc),
):
    """Attach a voiceover audio track to a render job."""
    job = await svc.attach_voiceover(render_id, body.voiceover_id, body.audio_path)
    return RenderJobResponse.from_model(job)


@router.post("/{render_id}/publish", response_model=RenderJobResponse)
async def publish_video(render_id: uuid.UUID, svc: RenderService = Depends(_svc)):
    """Publish the final video – generates a delivery URL (CDN stub).

    In production this uploads the final video (with voiceover audio mix)
    to an object store / CDN and returns the public URL for logistics retrieval.
    """
    job = await svc.publish_video(render_id)
    return RenderJobResponse.from_model(job)


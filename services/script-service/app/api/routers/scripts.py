"""Script generation endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import ScriptListResponse, ScriptResponse
from app.db.session import get_db
from app.services.script_service import ScriptService

router = APIRouter(prefix="/scripts", tags=["scripts"])


def _svc(db: Session = Depends(get_db)) -> ScriptService:
    return ScriptService(db)


@router.post("/generate", response_model=ScriptResponse, status_code=201)
async def generate_script(poi_id: uuid.UUID = Query(...), svc: ScriptService = Depends(_svc)):
    script = await svc.generate_script(poi_id)
    return ScriptResponse.from_model(script)


@router.get("", response_model=ScriptListResponse)
async def list_scripts(
    poi_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ScriptService = Depends(_svc),
):
    items, total = svc.list_scripts(poi_id=poi_id, page=page, page_size=page_size)
    return ScriptListResponse(items=[ScriptResponse.from_model(s) for s in items], total=total, page=page, page_size=page_size)


@router.get("/{script_id}", response_model=ScriptResponse)
async def get_script(script_id: uuid.UUID, svc: ScriptService = Depends(_svc)):
    return ScriptResponse.from_model(svc.get_script(script_id))


"""Asset CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import AssetCreate, AssetListResponse, AssetResponse, AssetUpdate
from app.db.session import get_db
from app.services.asset_service import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


def _svc(db: Session = Depends(get_db)) -> AssetService:
    return AssetService(db)


@router.post("", response_model=AssetResponse, status_code=201)
async def create_asset(body: AssetCreate, svc: AssetService = Depends(_svc)):
    asset = await svc.create_asset(body)
    return AssetResponse.from_model(asset)


@router.get("", response_model=AssetListResponse)
async def list_assets(
    poi_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: AssetService = Depends(_svc),
):
    items, total = svc.list_assets(poi_id=poi_id, page=page, page_size=page_size)
    return AssetListResponse(items=[AssetResponse.from_model(a) for a in items], total=total)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: uuid.UUID, svc: AssetService = Depends(_svc)):
    return AssetResponse.from_model(svc.get_asset(asset_id))


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(asset_id: uuid.UUID, body: AssetUpdate, svc: AssetService = Depends(_svc)):
    asset = await svc.update_asset(asset_id, body)
    return AssetResponse.from_model(asset)

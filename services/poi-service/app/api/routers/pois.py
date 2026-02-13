"""POI CRUD + workflow endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import POICreate, POIListResponse, POIResponse, POIUpdate
from app.db.session import get_db
from app.services.poi_service import POIService

router = APIRouter(prefix="/pois", tags=["pois"])


def _svc(db: Session = Depends(get_db)) -> POIService:
    return POIService(db)


@router.post("", response_model=POIResponse, status_code=201)
async def create_poi(body: POICreate, svc: POIService = Depends(_svc)):
    poi = await svc.create_poi(body)
    return POIResponse.from_model(poi)


@router.get("", response_model=POIListResponse)
async def list_pois(
    query: str | None = None,
    status: str | None = None,
    poi_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: POIService = Depends(_svc),
):
    items, total = svc.list_pois(query=query, status=status, poi_type=poi_type, page=page, page_size=page_size)
    return POIListResponse(
        items=[POIResponse.from_model(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{poi_id}", response_model=POIResponse)
async def get_poi(poi_id: uuid.UUID, svc: POIService = Depends(_svc)):
    return POIResponse.from_model(svc.get_poi(poi_id))


@router.patch("/{poi_id}", response_model=POIResponse)
async def update_poi(poi_id: uuid.UUID, body: POIUpdate, svc: POIService = Depends(_svc)):
    poi = await svc.update_poi(poi_id, body)
    return POIResponse.from_model(poi)


@router.post("/{poi_id}/validate", response_model=POIResponse)
async def validate_poi(poi_id: uuid.UUID, svc: POIService = Depends(_svc)):
    poi = await svc.validate_poi(poi_id)
    return POIResponse.from_model(poi)


@router.post("/{poi_id}/publish", response_model=POIResponse)
async def publish_poi(poi_id: uuid.UUID, svc: POIService = Depends(_svc)):
    poi = await svc.publish_poi(poi_id)
    return POIResponse.from_model(poi)


@router.post("/{poi_id}/archive", response_model=POIResponse)
async def archive_poi(poi_id: uuid.UUID, svc: POIService = Depends(_svc)):
    poi = await svc.archive_poi(poi_id)
    return POIResponse.from_model(poi)

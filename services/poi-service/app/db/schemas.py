"""Pydantic schemas for poi-service request / response bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class POICreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    address: str | None = None
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    poi_type: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class POIUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    poi_type: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class POIResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    address: str | None
    lat: float
    lon: float
    poi_type: str | None
    tags: list[str]
    metadata: dict[str, Any]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "POIResponse":
        return cls(
            id=obj.id,
            name=obj.name,
            description=obj.description,
            address=obj.address,
            lat=obj.lat,
            lon=obj.lon,
            poi_type=obj.poi_type,
            tags=obj.tags or [],
            metadata=obj.metadata_ or {},
            status=obj.status,
            version=obj.version,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class POIListResponse(BaseModel):
    items: list[POIResponse]
    total: int
    page: int
    page_size: int

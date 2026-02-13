"""Pydantic schemas for asset-service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    poi_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=500)
    asset_type: str = "photo"
    description: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    metadata: dict[str, Any] = {}


class AssetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    metadata: dict[str, Any] | None = None


class AssetResponse(BaseModel):
    id: uuid.UUID
    poi_id: uuid.UUID
    name: str
    asset_type: str
    description: str | None
    file_path: str | None
    mime_type: str | None
    file_size: int | None
    metadata: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, obj) -> "AssetResponse":
        return cls(
            id=obj.id,
            poi_id=obj.poi_id,
            name=obj.name,
            asset_type=obj.asset_type,
            description=obj.description,
            file_path=obj.file_path,
            mime_type=obj.mime_type,
            file_size=obj.file_size,
            metadata=obj.metadata_ or {},
            version=obj.version,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int

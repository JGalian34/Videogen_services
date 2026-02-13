"""Asset business-logic layer."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from contracts.events import AssetEventType

from app.db.models import Asset
from app.db.schemas import AssetCreate, AssetUpdate
from app.integrations.kafka_producer import publish_asset_event
from common.errors import NotFoundError

logger = logging.getLogger(__name__)


class AssetService:
    def __init__(self, db: Session):
        self.db = db

    async def create_asset(self, data: AssetCreate) -> Asset:
        asset = Asset(
            poi_id=data.poi_id,
            name=data.name,
            asset_type=data.asset_type,
            description=data.description,
            file_path=data.file_path,
            mime_type=data.mime_type,
            file_size=data.file_size,
            metadata_=data.metadata,
            version=1,
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)

        await publish_asset_event(AssetEventType.ASSET_CREATED, asset)
        logger.info("Asset created: %s for POI %s", asset.id, asset.poi_id)
        return asset

    def get_asset(self, asset_id: uuid.UUID) -> Asset:
        asset = self.db.get(Asset, asset_id)
        if not asset:
            raise NotFoundError(f"Asset {asset_id} not found")
        return asset

    def list_assets(
        self,
        *,
        poi_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Asset], int]:
        q = self.db.query(Asset)
        if poi_id:
            q = q.filter(Asset.poi_id == poi_id)
        total = q.count()
        items = q.order_by(Asset.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    async def update_asset(self, asset_id: uuid.UUID, data: AssetUpdate) -> Asset:
        asset = self.get_asset(asset_id)

        if data.name is not None:
            asset.name = data.name
        if data.description is not None:
            asset.description = data.description
        if data.file_path is not None:
            asset.file_path = data.file_path
        if data.mime_type is not None:
            asset.mime_type = data.mime_type
        if data.file_size is not None:
            asset.file_size = data.file_size
        if data.metadata is not None:
            asset.metadata_ = data.metadata

        asset.version += 1
        self.db.commit()
        self.db.refresh(asset)

        await publish_asset_event(AssetEventType.ASSET_UPDATED, asset)
        logger.info("Asset updated: %s v%d", asset.id, asset.version)
        return asset

"""
POI business-logic layer.

Handles:
  - CRUD
  - Status workflow (draft → validated → published → archived)
  - Version bumping on published edits
  - Event publishing to Redpanda
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from contracts.events import POIEventType

from app.db.models import POI, POIStatus
from app.db.schemas import POICreate, POIUpdate
from app.integrations.kafka_producer import publish_poi_event
from common.errors import NotFoundError, WorkflowError

logger = logging.getLogger(__name__)

# Valid status transitions
_TRANSITIONS: dict[str, set[str]] = {
    POIStatus.DRAFT.value: {POIStatus.VALIDATED.value},
    POIStatus.VALIDATED.value: {POIStatus.PUBLISHED.value, POIStatus.DRAFT.value},
    POIStatus.PUBLISHED.value: {POIStatus.ARCHIVED.value},
    POIStatus.ARCHIVED.value: set(),
}


class POIService:
    def __init__(self, db: Session):
        self.db = db

    # ── Create ──────────────────────────────────────────────────────────
    async def create_poi(self, data: POICreate) -> POI:
        poi = POI(
            name=data.name,
            description=data.description,
            address=data.address,
            lat=data.lat,
            lon=data.lon,
            poi_type=data.poi_type,
            tags=data.tags,
            metadata_=data.metadata,
            status=POIStatus.DRAFT.value,
            version=1,
        )
        self.db.add(poi)
        self.db.commit()
        self.db.refresh(poi)

        await publish_poi_event(POIEventType.POI_CREATED, poi)
        logger.info("POI created: %s", poi.id)
        return poi

    # ── Read ────────────────────────────────────────────────────────────
    def get_poi(self, poi_id: uuid.UUID) -> POI:
        poi = self.db.get(POI, poi_id)
        if not poi:
            raise NotFoundError(f"POI {poi_id} not found")
        return poi

    def list_pois(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        poi_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[POI], int]:
        q = self.db.query(POI)

        if query:
            q = q.filter(
                or_(
                    POI.name.ilike(f"%{query}%"),
                    POI.address.ilike(f"%{query}%"),
                    POI.description.ilike(f"%{query}%"),
                )
            )
        if status:
            q = q.filter(POI.status == status)
        if poi_type:
            q = q.filter(POI.poi_type == poi_type)

        total = q.count()
        items = q.order_by(POI.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    # ── Update ──────────────────────────────────────────────────────────
    async def update_poi(self, poi_id: uuid.UUID, data: POIUpdate) -> POI:
        poi = self.get_poi(poi_id)

        if poi.status == POIStatus.PUBLISHED.value:
            poi.version += 1

        if data.name is not None:
            poi.name = data.name
        if data.description is not None:
            poi.description = data.description
        if data.address is not None:
            poi.address = data.address
        if data.lat is not None:
            poi.lat = data.lat
        if data.lon is not None:
            poi.lon = data.lon
        if data.poi_type is not None:
            poi.poi_type = data.poi_type
        if data.tags is not None:
            poi.tags = data.tags
        if data.metadata is not None:
            poi.metadata_ = data.metadata

        self.db.commit()
        self.db.refresh(poi)

        await publish_poi_event(POIEventType.POI_UPDATED, poi)
        logger.info("POI updated: %s v%d", poi.id, poi.version)
        return poi

    # ── Workflow: Validate ──────────────────────────────────────────────
    async def validate_poi(self, poi_id: uuid.UUID) -> POI:
        poi = self.get_poi(poi_id)
        self._check_transition(poi, POIStatus.VALIDATED.value)

        if not (-90 <= poi.lat <= 90 and -180 <= poi.lon <= 180):
            raise WorkflowError("Cannot validate: invalid coordinates.")

        poi.status = POIStatus.VALIDATED.value
        self.db.commit()
        self.db.refresh(poi)

        await publish_poi_event(POIEventType.POI_VALIDATED, poi)
        logger.info("POI validated: %s", poi.id)
        return poi

    # ── Workflow: Publish ───────────────────────────────────────────────
    async def publish_poi(self, poi_id: uuid.UUID) -> POI:
        poi = self.get_poi(poi_id)
        self._check_transition(poi, POIStatus.PUBLISHED.value)

        poi.status = POIStatus.PUBLISHED.value
        self.db.commit()
        self.db.refresh(poi)

        await publish_poi_event(POIEventType.POI_PUBLISHED, poi)
        logger.info("POI published: %s", poi.id)
        return poi

    # ── Workflow: Archive ───────────────────────────────────────────────
    async def archive_poi(self, poi_id: uuid.UUID) -> POI:
        poi = self.get_poi(poi_id)
        self._check_transition(poi, POIStatus.ARCHIVED.value)

        poi.status = POIStatus.ARCHIVED.value
        self.db.commit()
        self.db.refresh(poi)

        await publish_poi_event(POIEventType.POI_ARCHIVED, poi)
        logger.info("POI archived: %s", poi.id)
        return poi

    # ── Internal ────────────────────────────────────────────────────────
    @staticmethod
    def _check_transition(poi: POI, target: str) -> None:
        allowed = _TRANSITIONS.get(poi.status, set())
        if target not in allowed:
            raise WorkflowError(f"Cannot transition from '{poi.status}' to '{target}'. " f"Allowed: {sorted(allowed)}")

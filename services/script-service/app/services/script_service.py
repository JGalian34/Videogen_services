"""
Script generation business-logic layer.

Fetches POI + assets from upstream services, then uses an NLP provider
(stub by default) to generate a structured VideoScript.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from contracts.events import VideoEventType

from app.core.config import ASSET_SERVICE_URL, POI_SERVICE_URL, NLP_PROVIDER
from app.db.models import VideoScript
from app.integrations.kafka_producer import publish_video_event
from app.integrations.nlp_provider import get_nlp_provider
from common.errors import AppError
from common.http_client import ServiceClient

logger = logging.getLogger(__name__)

_poi_client = ServiceClient(POI_SERVICE_URL)
_asset_client = ServiceClient(ASSET_SERVICE_URL)


class ScriptService:
    def __init__(self, db: Session):
        self.db = db

    async def generate_script(self, poi_id: uuid.UUID) -> VideoScript:
        # 1) Fetch POI data
        poi_resp = await _poi_client.get(f"/pois/{poi_id}")
        if poi_resp.status_code != 200:
            raise AppError(f"POI {poi_id} not found in poi-service (HTTP {poi_resp.status_code})")
        poi_data = poi_resp.json()

        # 2) Fetch assets for this POI
        assets_resp = await _asset_client.get("/assets", params={"poi_id": str(poi_id)})
        assets_data = assets_resp.json().get("items", []) if assets_resp.status_code == 200 else []

        # 3) Generate script via NLP provider
        provider = get_nlp_provider(NLP_PROVIDER)
        script_output = await provider.generate(poi_data, assets_data)

        # 4) Persist
        script = VideoScript(
            poi_id=poi_id,
            title=script_output["title"],
            tone=script_output.get("tone", "warm"),
            total_duration_seconds=script_output.get("total_duration_seconds", 30.0),
            scenes=script_output["scenes"],
            narration_text=script_output.get("narration_text"),
            nlp_provider=NLP_PROVIDER,
            metadata_={"poi_name": poi_data.get("name"), "asset_count": len(assets_data)},
            version=1,
        )
        self.db.add(script)
        self.db.commit()
        self.db.refresh(script)

        # 5) Publish event
        await publish_video_event(VideoEventType.SCRIPT_GENERATED, script)
        logger.info("Script generated: %s for POI %s", script.id, poi_id)
        return script

    def get_script(self, script_id: uuid.UUID) -> VideoScript:
        from common.errors import NotFoundError

        script = self.db.get(VideoScript, script_id)
        if not script:
            raise NotFoundError(f"Script {script_id} not found")
        return script

    def list_scripts(
        self, *, poi_id: uuid.UUID | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[VideoScript], int]:
        q = self.db.query(VideoScript)
        if poi_id:
            q = q.filter(VideoScript.poi_id == poi_id)
        total = q.count()
        items = q.order_by(VideoScript.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total


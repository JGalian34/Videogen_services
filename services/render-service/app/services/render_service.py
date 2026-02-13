"""
Render business-logic layer.

Processes script scenes via a RunwayClient provider (stub by default).
Each scene is rendered individually; a ``render.scene.generated`` event is
published for each, and ``render.completed`` when all are done.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from contracts.events import VideoEventType

from app.db.models import RenderJob, RenderScene, RenderStatus
from app.integrations.kafka_producer import publish_video_event
from app.integrations.runway_client import get_runway_client
from common.errors import NotFoundError

logger = logging.getLogger(__name__)


class RenderService:
    def __init__(self, db: Session):
        self.db = db

    async def create_render_from_script_event(self, payload: dict) -> RenderJob:
        """Called when a ``script.generated`` event is consumed."""
        script_id = uuid.UUID(payload["script_id"])
        poi_id = uuid.UUID(payload["poi_id"])
        scene_count = payload.get("scene_count", 0)

        job = RenderJob(
            poi_id=poi_id,
            script_id=script_id,
            status=RenderStatus.PENDING.value,
            total_scenes=scene_count,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info("Render job created: %s for script %s", job.id, script_id)

        # Process scenes (uses stub by default)
        await self._process_scenes(job, payload)
        return job

    async def _process_scenes(self, job: RenderJob, payload: dict) -> None:
        """Render each scene using the configured Runway provider."""
        job.status = RenderStatus.PROCESSING.value
        self.db.commit()

        client = get_runway_client()
        scenes_data = payload.get("scenes", [])

        # If no scene details in event, create placeholder scenes
        if not scenes_data:
            scenes_data = [
                {"scene_number": i + 1, "title": f"Scene {i + 1}", "visual_prompt": "", "duration_seconds": 5.0}
                for i in range(job.total_scenes or 6)
            ]

        for scene_data in scenes_data:
            scene = RenderScene(
                render_job_id=job.id,
                scene_number=scene_data.get("scene_number", 1),
                title=scene_data.get("title", "Untitled"),
                visual_prompt=scene_data.get("visual_prompt", ""),
                duration_seconds=scene_data.get("duration_seconds", 5.0),
            )
            self.db.add(scene)
            self.db.commit()
            self.db.refresh(scene)

            # Render scene
            result = await client.generate_scene(scene.visual_prompt or "", scene.duration_seconds)

            scene.status = RenderStatus.COMPLETED.value
            scene.output_path = result.get("output_path")
            scene.provider = result.get("provider", "stub")
            scene.cost = result.get("cost", 0.0)
            self.db.commit()

            job.completed_scenes += 1
            self.db.commit()

            await publish_video_event(VideoEventType.RENDER_SCENE_GENERATED, {
                "render_job_id": str(job.id),
                "scene_id": str(scene.id),
                "scene_number": scene.scene_number,
                "poi_id": str(job.poi_id),
            })

        # Mark job complete
        job.status = RenderStatus.COMPLETED.value
        job.completed_at = datetime.now(timezone.utc)
        job.output_path = f"/data/renders/{job.id}/final.mp4"
        self.db.commit()
        self.db.refresh(job)

        await publish_video_event(VideoEventType.RENDER_COMPLETED, {
            "render_job_id": str(job.id),
            "poi_id": str(job.poi_id),
            "script_id": str(job.script_id),
            "total_scenes": job.total_scenes,
        })
        logger.info("Render completed: %s (%d scenes)", job.id, job.completed_scenes)

    async def attach_voiceover(self, render_id: uuid.UUID, voiceover_id: str, audio_path: str) -> RenderJob:
        """Associate a voiceover audio track with a render job."""
        job = self.get_render(render_id)
        job.voiceover_id = voiceover_id
        job.voiceover_audio_path = audio_path
        self.db.commit()
        self.db.refresh(job)
        logger.info("Voiceover attached to render %s: %s", render_id, audio_path)
        return job

    async def publish_video(self, render_id: uuid.UUID) -> RenderJob:
        """Mark a render as published and generate a delivery URL.

        In production, this would upload to CDN / S3 / GCS.
        In stub mode, it generates a local URL.
        """
        from common.errors import WorkflowError

        job = self.get_render(render_id)
        if job.status != RenderStatus.COMPLETED.value:
            raise WorkflowError(f"Can only publish completed renders (current: {job.status})")

        # Stub: generate a delivery URL (in production, upload to CDN)
        job.published_url = f"https://cdn.poi-video.example.com/videos/{job.id}/final.mp4"
        job.published_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)

        await publish_video_event(VideoEventType.VIDEO_PUBLISHED, {
            "render_job_id": str(job.id),
            "poi_id": str(job.poi_id),
            "script_id": str(job.script_id),
            "published_url": job.published_url,
            "voiceover_audio_path": job.voiceover_audio_path,
        })
        logger.info("Video published: %s → %s", job.id, job.published_url)
        return job

    async def retry_render(self, render_id: uuid.UUID) -> RenderJob:
        job = self.get_render(render_id)
        if job.status != RenderStatus.FAILED.value:
            from common.errors import WorkflowError

            raise WorkflowError(f"Can only retry failed renders (current: {job.status})")

        job.status = RenderStatus.PENDING.value
        job.completed_scenes = 0
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)

        logger.info("Render retried: %s", job.id)
        return job

    def get_render(self, render_id: uuid.UUID) -> RenderJob:
        job = self.db.get(RenderJob, render_id)
        if not job:
            raise NotFoundError(f"Render job {render_id} not found")
        return job

    def list_renders(
        self, *, poi_id: uuid.UUID | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[RenderJob], int]:
        q = self.db.query(RenderJob)
        if poi_id:
            q = q.filter(RenderJob.poi_id == poi_id)
        total = q.count()
        items = q.order_by(RenderJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total


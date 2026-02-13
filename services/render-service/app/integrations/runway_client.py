"""
Runway video generation client.

Supports two modes:
  - ``stub`` (default): no external API calls, returns placeholder data
  - ``live``: calls the real Runway API (requires RUNWAY_API_KEY env var)

Switch via RUNWAY_MODE environment variable.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import uuid
from typing import Any

from app.core.config import RUNWAY_API_KEY, RUNWAY_API_URL, RUNWAY_MODE

logger = logging.getLogger(__name__)


class RunwayClient(abc.ABC):
    @abc.abstractmethod
    async def generate_scene(self, prompt: str, duration_seconds: float) -> dict[str, Any]:
        """Generate a single scene video. Returns dict with output_path, provider, cost."""
        ...


class StubRunwayClient(RunwayClient):
    """Returns placeholder data without making any API call."""

    async def generate_scene(self, prompt: str, duration_seconds: float) -> dict[str, Any]:
        # Simulate processing time
        await asyncio.sleep(0.05)
        scene_id = str(uuid.uuid4())[:8]
        return {
            "output_path": f"/data/renders/stub_{scene_id}.mp4",
            "provider": "stub",
            "cost": 0.0,
            "duration_seconds": duration_seconds,
            "prompt": prompt[:100],
        }


class LiveRunwayClient(RunwayClient):
    """Calls the real Runway ML API."""

    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url

    async def generate_scene(self, prompt: str, duration_seconds: float) -> dict[str, Any]:
        import httpx

        if not self.api_key:
            logger.error("RUNWAY_API_KEY not set – falling back to stub")
            return await StubRunwayClient().generate_scene(prompt, duration_seconds)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.api_url}/generations",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "prompt": prompt,
                        "duration": int(duration_seconds),
                        "model": "gen-3",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "output_path": data.get("output_url", ""),
                    "provider": "runway",
                    "cost": data.get("cost", 0.5),
                    "duration_seconds": duration_seconds,
                }
        except Exception as exc:
            logger.error("Runway API error: %s – falling back to stub", exc)
            return await StubRunwayClient().generate_scene(prompt, duration_seconds)


def get_runway_client() -> RunwayClient:
    if RUNWAY_MODE == "live":
        return LiveRunwayClient(api_key=RUNWAY_API_KEY, api_url=RUNWAY_API_URL)
    return StubRunwayClient()

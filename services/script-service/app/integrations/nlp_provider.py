"""
NLP Provider abstraction for script generation.

Supports:
  - ``stub``: deterministic local generation (default, no external deps)
  - ``openai``: placeholder for real OpenAI integration
"""

from __future__ import annotations

import abc
from typing import Any


class NLPProvider(abc.ABC):
    @abc.abstractmethod
    async def generate(self, poi_data: dict, assets_data: list[dict]) -> dict[str, Any]:
        """Return a dict with keys: title, tone, total_duration_seconds, scenes, narration_text."""
        ...


class StubNLPProvider(NLPProvider):
    """Generates a deterministic script without any external API call."""

    async def generate(self, poi_data: dict, assets_data: list[dict]) -> dict[str, Any]:
        name = poi_data.get("name", "Unknown POI")
        address = poi_data.get("address", "")
        description = poi_data.get("description", "")

        scenes = [
            {
                "scene_number": 1,
                "title": "Establishing Shot",
                "description": f"Aerial view approaching {name}",
                "duration_seconds": 5.0,
                "asset_id": assets_data[0]["id"] if assets_data else None,
                "visual_prompt": f"Cinematic aerial shot of {address or name}, golden hour",
            },
            {
                "scene_number": 2,
                "title": "Exterior Detail",
                "description": f"Close-up of the exterior of {name}",
                "duration_seconds": 5.0,
                "asset_id": assets_data[1]["id"] if len(assets_data) > 1 else None,
                "visual_prompt": f"Detailed exterior shot of {name}, warm lighting",
            },
            {
                "scene_number": 3,
                "title": "Interior Highlight",
                "description": f"Walk-through interior of {name}",
                "duration_seconds": 5.0,
                "asset_id": None,
                "visual_prompt": "Smooth interior walk-through of a real estate property",
            },
            {
                "scene_number": 4,
                "title": "Neighbourhood",
                "description": f"Surroundings and neighbourhood of {name}",
                "duration_seconds": 5.0,
                "asset_id": None,
                "visual_prompt": f"Street-level view of the neighbourhood near {address}",
            },
            {
                "scene_number": 5,
                "title": "Lifestyle",
                "description": f"Lifestyle and ambiance around {name}",
                "duration_seconds": 5.0,
                "asset_id": None,
                "visual_prompt": "People enjoying local cafes and parks, warm atmosphere",
            },
            {
                "scene_number": 6,
                "title": "Closing",
                "description": f"Final panoramic view of {name}",
                "duration_seconds": 5.0,
                "asset_id": None,
                "visual_prompt": f"Sunset panoramic view of {name}, cinematic ending",
            },
        ]

        narration = (
            f"Discover {name}. {description or ''} "
            f"Located at {address or 'a prime location'}, "
            f"this property offers an exceptional living experience. "
            f"From the stunning exterior to the refined interiors, "
            f"every detail has been crafted with care."
        )

        return {
            "title": f"Video Script – {name}",
            "tone": "warm",
            "total_duration_seconds": 30.0,
            "scenes": scenes,
            "narration_text": narration.strip(),
        }


class OpenAINLPProvider(NLPProvider):
    """Placeholder for OpenAI-based script generation."""

    async def generate(self, poi_data: dict, assets_data: list[dict]) -> dict[str, Any]:
        # In production, this would call the OpenAI API
        # For now, fall back to stub
        stub = StubNLPProvider()
        return await stub.generate(poi_data, assets_data)


def get_nlp_provider(name: str = "stub") -> NLPProvider:
    providers = {
        "stub": StubNLPProvider,
        "openai": OpenAINLPProvider,
    }
    cls = providers.get(name, StubNLPProvider)
    return cls()

"""
Base HTTP client that propagates ``X-Correlation-Id`` and ``X-API-Key``
headers to other microservices.
"""

from __future__ import annotations

import httpx

from common.config import API_KEY
from common.middleware.correlation import HEADER_NAME, get_correlation_id


class ServiceClient:
    """Thin wrapper around httpx.AsyncClient for inter-service calls."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            HEADER_NAME: get_correlation_id(),
            "X-API-Key": API_KEY,
        }

    async def get(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.get(f"{self.base_url}{path}", headers=self._headers(), **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(f"{self.base_url}{path}", headers=self._headers(), **kwargs)

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.patch(f"{self.base_url}{path}", headers=self._headers(), **kwargs)

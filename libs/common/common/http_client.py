"""
Base HTTP client that propagates ``X-Correlation-Id`` and ``X-API-Key``
headers to other microservices.

Uses a *persistent* ``httpx.AsyncClient`` per ``ServiceClient`` instance
to benefit from connection pooling and keep-alive.  The client is created
lazily on first use and closed via :meth:`close`.

Timeouts and retries are configurable; infinite retry loops are prevented
by a bounded retry count with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from common.config import API_KEY
from common.middleware.correlation import HEADER_NAME, get_correlation_id

logger = logging.getLogger(__name__)

# Defaults
_DEFAULT_TIMEOUT = 10.0
_MAX_RETRIES = 2
_BACKOFF_BASE = 0.3


class ServiceClient:
    """Thin wrapper around httpx.AsyncClient for inter-service calls.

    Connection pooling is managed by a single ``httpx.AsyncClient``
    instance per ``ServiceClient`` – no new client is created per request.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily initialise the persistent async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=30,
                ),
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            HEADER_NAME: get_correlation_id(),
            "X-API-Key": API_KEY,
        }

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute an HTTP request with bounded retries + exponential backoff."""
        client = self._get_client()
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.request(
                    method,
                    path,
                    headers=self._headers(),
                    **kwargs,
                )
                return resp
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = _BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "HTTP %s %s%s failed (attempt %d/%d): %s – retrying in %.1fs",
                        method,
                        self.base_url,
                        path,
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
            except httpx.HTTPError as exc:
                # Non-retriable HTTP errors
                raise exc

        # All retries exhausted
        raise last_exc  # type: ignore[misc]

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("PATCH", path, **kwargs)

    async def close(self) -> None:
        """Close the underlying HTTP client (releases connections)."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

"""
Simple API-Key authentication middleware.

Reads ``X-API-Key`` header and compares against the configured key.
Health-check endpoints are excluded.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from common.config import API_KEY

_PUBLIC_PATHS = {"/healthz", "/readyz", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return JSONResponse(
                status_code=401,
                content={"error": "auth_error", "detail": "Invalid or missing API key"},
            )

        return await call_next(request)

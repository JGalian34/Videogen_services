"""
Request body size-limiting middleware.

Rejects payloads exceeding ``MAX_BODY_BYTES`` with HTTP 413.
Protects services from memory exhaustion under adversarial load.
"""

from __future__ import annotations

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024)))  # 10 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "payload_too_large",
                    "detail": f"Request body exceeds {MAX_BODY_BYTES} bytes",
                },
            )
        return await call_next(request)

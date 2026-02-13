"""
Correlation-ID middleware for FastAPI.

Reads ``X-Correlation-Id`` from the incoming request (or creates a new UUID4)
and stores it in a context variable so that every log line and outgoing call
can propagate it.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HEADER_NAME = "X-Correlation-Id"

_correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return _correlation_id_ctx.get("")


def set_correlation_id(value: str) -> None:
    _correlation_id_ctx.set(value)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cid = request.headers.get(HEADER_NAME) or str(uuid.uuid4())
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers[HEADER_NAME] = cid
        return response

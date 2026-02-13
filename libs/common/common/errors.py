"""
Shared error types and FastAPI exception handlers.

Every service registers these handlers in its ``main.py`` so all error
responses have a consistent shape:

    { "error": "<type>", "detail": "<message>" }
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ── Base errors ────────────────────────────────────────────────────────

class AppError(Exception):
    """Generic application error (400)."""

    def __init__(self, detail: str = "Bad request"):
        self.detail = detail


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, detail: str = "Not found"):
        self.detail = detail


class WorkflowError(AppError):
    """Invalid status transition (409)."""

    def __init__(self, detail: str = "Invalid workflow transition"):
        self.detail = detail


class AuthError(AppError):
    """Authentication / authorisation failure (401/403)."""

    def __init__(self, detail: str = "Unauthorized"):
        self.detail = detail


# ── Handlers ───────────────────────────────────────────────────────────

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": exc.detail})

    @app.exception_handler(WorkflowError)
    async def _workflow(request: Request, exc: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "workflow_error", "detail": exc.detail})

    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "auth_error", "detail": exc.detail})

    @app.exception_handler(AppError)
    async def _app(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "app_error", "detail": exc.detail})

    @app.exception_handler(ValueError)
    async def _value(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("common.errors").exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": "An unexpected error occurred"},
        )


"""Request context middleware – request_id propagation and timing."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response

from app.config.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


def register_request_context(app: FastAPI) -> None:
    """Add HTTP middleware that propagates *request_id* and logs timing."""

    @app.middleware("http")
    async def _ctx(request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        start = time.monotonic()

        try:
            response: Response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )
            response.headers["x-request-id"] = request_id
            return response
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(
                "http.request.error",
                method=request.method,
                path=request.url.path,
                exception=type(exc).__name__,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
                exc_info=True,
            )
            raise
        finally:
            request_id_ctx.reset(token)

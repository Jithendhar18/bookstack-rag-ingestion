"""Standardised error handling for the API.

Registers global exception handlers that convert all errors into the
``{"error": {"code": "…", "message": "…", "details": {}}}`` format.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.utils import APIException
from app.config.logging import get_logger
from app.domain.exceptions import DomainException

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to *app*."""

    @app.exception_handler(APIException)
    async def _api_exception(request: Request, exc: APIException) -> JSONResponse:
        logger.warning(
            "api.exception",
            status_code=exc.status_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": type(exc).__name__.upper(),
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(DomainException)
    async def _domain_exception(request: Request, exc: DomainException) -> JSONResponse:
        logger.warning(
            "domain.exception",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": {},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("validation.error", path=request.url.path, errors=str(exc.errors()))
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled.exception",
            path=request.url.path,
            exception=type(exc).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": {},
                }
            },
        )

"""FastAPI application for RAG query API.

This module initializes and configures the FastAPI application including:
- Route registration (health checks, query endpoints)
- Dependency injection setup
- Middleware for structured logging and CORS
- Request ID propagation
- Graceful startup/shutdown of services
"""

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.routes import chat, health, ingestion, query
from app.api.utils import APIException
from app.config.logging import get_logger, request_id_ctx, setup_logging
from app.config.settings import get_settings
from app.domain.exceptions import DomainException

logger = get_logger(__name__)


async def initialize_services() -> None:
    """Initialize application services."""
    logger.info("services.initializing")
    settings = get_settings()
    logger.info(
        "services.initialized",
        environment=settings.environment.value,
        debug=settings.debug,
    )


async def shutdown_services() -> None:
    """Shutdown application services — dispose connection pools and clear caches."""
    logger.info("services.shutting_down")

    # Clear cached singleton services
    from app.api.dependencies import (
        _get_bookstack_client,
        _get_embedding_service,
        _get_vector_store,
    )

    for cache_fn in (_get_embedding_service, _get_vector_store, _get_bookstack_client):
        try:
            cache_fn.cache_clear()
        except Exception as exc:
            logger.warning("services.cache_clear_failed", error=str(exc))

    # Dispose database engine pools
    try:
        from app.db.session import get_session_manager

        get_session_manager().engine.dispose()
        logger.info("services.db_engine_disposed", source="app.db.session")
    except Exception as exc:
        logger.warning("services.db_dispose_failed", source="app.db.session", error=str(exc))

    try:
        from app.infrastructure.database.session import get_session_manager as get_infra_manager

        get_infra_manager().engine.dispose()
        logger.info("services.db_engine_disposed", source="infrastructure")
    except Exception as exc:
        logger.warning("services.db_dispose_failed", source="infrastructure", error=str(exc))

    logger.info("services.shutdown_complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    await initialize_services()
    yield
    # Shutdown
    await shutdown_services()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    # Initialize structured logging before anything else
    setup_logging(
        log_level=settings.log_level,
        json_output=settings.log_json,
    )

    app = FastAPI(
        title=settings.api.title,
        description="Production-grade Retrieval-Augmented Generation API for BookStack documentation",
        version=settings.api.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request logging middleware with request_id propagation
    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable) -> Response:
        """Log HTTP requests with timing and propagate request_id."""
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

    # Register routes
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(query.router, prefix="/query", tags=["query"])
    app.include_router(ingestion.router, tags=["ingestion"])
    app.include_router(chat.router, tags=["chat"])

    # ---------------------------------------------------------------------- #
    # Global exception handlers
    # ---------------------------------------------------------------------- #
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
        logger.warning(
            "api.exception",
            status_code=exc.status_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
        logger.warning(
            "domain.exception",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "code": exc.code},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("validation.error", path=request.url.path, errors=str(exc.errors()))
        return JSONResponse(
            status_code=422,
            content={"error": "Validation error", "details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled.exception",
            path=request.url.path,
            exception=type(exc).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    # Custom OpenAPI schema
    def custom_openapi():
        """Generate custom OpenAPI schema with examples."""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # Add info about features
        openapi_schema["info"]["x-features"] = [
            "Vector similarity search with metadata filtering",
            "Optional cross-encoder reranking",
            "LLM-based answer generation",
            "Query result caching",
            "Batch query processing",
            "Request tracing with IDs",
        ]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # Root endpoint
    @app.get("/", tags=["info"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": app.title,
            "version": app.version,
            "description": app.description,
            "endpoints": {
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "health": "/health/",
                "health_ready": "/health/ready",
                "ingestion_run": "POST /ingestion/run",
                "ingestion_runs": "GET /ingestion/runs",
                "ingestion_stats": "GET /ingestion/stats",
                "query": "POST /query/",
                "query_batch": "POST /query/batch",
                "chat_session_create": "POST /chat/session",
                "chat_message": "POST /chat/message",
                "chat_history": "GET /chat/session/{session_id}",
                "chat_sessions": "GET /chat/sessions",
                "chat_ws": "WS /chat/ws/{session_id}",
            },
            "settings": {
                "enable_chat": settings.enable_chat,
                "enable_reranking": settings.enable_reranking,
                "enable_llm_generation": settings.enable_llm_generation,
                "enable_query_cache": settings.enable_query_cache,
                "top_k_default": settings.top_k_default,
                "embedding_model": settings.embedding_model,
                "environment": settings.environment,
            },
        }

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    setup_logging(
        log_level=settings.log_level,
        json_output=settings.log_json,
    )

    logger.info(
        "server.starting",
        host=settings.api_host,
        port=settings.api_port,
        environment=settings.environment.value,
        debug=settings.debug,
    )

    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

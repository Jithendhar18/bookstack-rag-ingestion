"""FastAPI application for RAG query API.

This module initializes and configures the FastAPI application including:
- API versioning (/api/v1/)
- Route registration (health, query, ingestion, chat, metrics)
- Standardised error handling
- Middleware for structured logging, CORS, and request_id propagation
- Graceful startup/shutdown of services
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.middleware.error_handler import register_error_handlers
from app.api.middleware.request_context import register_request_context
from app.api.routes import health as legacy_health
from app.api.routes.v1 import chat as v1_chat
from app.api.routes.v1 import ingestion as v1_ingestion
from app.api.routes.v1 import metrics as v1_metrics
from app.api.routes.v1 import query as v1_query
from app.config.logging import get_logger, setup_logging
from app.config.settings import get_settings

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

    # ── Middleware ─────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request-id propagation + timing logs
    register_request_context(app)

    # ── Standardised error handlers ───────────────────────────────
    register_error_handlers(app)

    # ── V1 API routes (/api/v1/…) ─────────────────────────────────
    app.include_router(v1_query.router, prefix="/api/v1", tags=["query"])
    app.include_router(v1_ingestion.router, prefix="/api/v1", tags=["ingestion"])
    app.include_router(v1_chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(v1_metrics.router, prefix="/api/v1", tags=["metrics"])

    # Health lives outside the versioned prefix (standard k8s convention)
    app.include_router(legacy_health.router, prefix="", tags=["health"])

    # ── Custom OpenAPI schema ─────────────────────────────────────
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema["info"]["x-features"] = [
            "API versioning (/api/v1)",
            "SSE streaming chat responses",
            "Async background ingestion",
            "Page-based pagination",
            "Vector similarity search with metadata filtering",
            "Optional cross-encoder reranking",
            "LLM-based answer generation",
            "Query result caching",
            "Request tracing with IDs",
            "Observability metrics",
        ]
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # ── Root endpoint ─────────────────────────────────────────────
    @app.get("/", tags=["info"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": app.title,
            "version": app.version,
            "description": app.description,
            "api_prefix": "/api/v1",
            "endpoints": {
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "health": "/health/",
                "health_ready": "/health/ready",
                "query": "POST /api/v1/query",
                "ingestion_run": "POST /api/v1/ingestion/run",
                "ingestion_runs": "GET /api/v1/ingestion/runs",
                "ingestion_run_status": "GET /api/v1/ingestion/run/{run_id}/status",
                "ingestion_stats": "GET /api/v1/ingestion/stats",
                "chat_session_create": "POST /api/v1/chat/session",
                "chat_message": "POST /api/v1/chat/message",
                "chat_stream": "POST /api/v1/chat/message/stream",
                "chat_history": "GET /api/v1/chat/session/{session_id}",
                "chat_sessions": "GET /api/v1/chat/sessions",
                "chat_ws": "WS /api/v1/chat/ws/{session_id}",
                "metrics": "GET /api/v1/metrics",
                "metrics_queries": "GET /api/v1/metrics/queries",
                "metrics_ingestion": "GET /api/v1/metrics/ingestion",
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

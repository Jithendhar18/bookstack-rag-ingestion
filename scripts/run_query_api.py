#!/usr/bin/env python
"""Run the RAG Query API server.

This script starts the FastAPI server for the BookStack RAG Query API.

Usage:
    python scripts/run_query_api.py

Environment Variables:
    API_HOST: Server host (default: 0.0.0.0)
    API_PORT: Server port (default: 8001)
    DEBUG: Enable debug mode (default: false)
    ENVIRONMENT: Environment name (default: production)
    CORS_ORIGINS: Comma-separated CORS origins (default: *)
    LOG_LEVEL: Logging level (default: INFO)
    LOG_JSON: JSON log output (default: false)

All other environment variables required for the ingestion pipeline are also required
(see app/config/settings.py for full list).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import get_logger, setup_logging

if __name__ == "__main__":
    import uvicorn

    from app.api.main import app
    from app.config.settings import get_settings

    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=settings.log_json)
    logger = get_logger(__name__)

    logger.info(
        "server.starting",
        host=settings.api_host,
        port=settings.api_port,
        environment=settings.environment.value,
        debug=settings.debug,
        reranking=settings.enable_reranking,
        llm_generation=settings.enable_llm_generation,
        query_cache=settings.enable_query_cache,
    )

    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

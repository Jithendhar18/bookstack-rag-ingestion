#!/usr/bin/env python
"""Complete BookStack RAG API server with all features.

This script runs the production-grade RAG API with:
- Ingestion control (sync management)
- Query/semantic search (with optional reranking)
- Chat system (multi-turn conversations)
- Health monitoring
- Observability and metrics
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> None:
    """Start the BookStack RAG API server."""
    try:
        import uvicorn

        from app.api.main import app
        from app.config.settings import get_settings

        settings = get_settings()
        setup_logging(log_level=settings.log_level, json_output=settings.log_json)

        logger.info(
            "server.starting",
            host=settings.api_host,
            port=settings.api_port,
            environment=settings.environment.value,
            debug=settings.debug,
            chat=settings.enable_chat,
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

    except Exception as e:
        logger.error("server.start_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

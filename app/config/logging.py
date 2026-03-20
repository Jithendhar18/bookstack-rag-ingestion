"""Centralized structured logging configuration.

Provides consistent, production-ready logging across the entire application
using structlog for structured output with request_id propagation.

Usage::

    from app.config.logging import setup_logging, get_logger

    # Call once at startup
    setup_logging(log_level="INFO", json_output=False)

    # Per-module logger (replaces logging.getLogger(__name__))
    logger = get_logger(__name__)
    logger.info("document.processed", page_id=42, chunks=12, duration_ms=340.5)

Context variables (request_id, run_id) are propagated automatically
via structlog's contextvars integration.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# ─── Context Variables ───────────────────────────────────────────────
# These are automatically included in every log line within a context.

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_ctx: ContextVar[int | str | None] = ContextVar("run_id", default=None)


def _inject_context_vars(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor: inject context variables into every log entry."""
    rid = request_id_ctx.get(None)
    if rid is not None:
        event_dict.setdefault("request_id", rid)

    run = run_id_ctx.get(None)
    if run is not None:
        event_dict.setdefault("run_id", run)

    return event_dict


def setup_logging(
    *,
    log_level: str = "INFO",
    json_output: bool = False,
    log_third_party_level: str = "WARNING",
) -> None:
    """Configure structured logging for the application.

    Call this once at application startup (before any loggers are used).

    Args:
        log_level: Root log level for the ``app`` namespace.
        json_output: If True, emit JSON lines (for production log aggregators).
                     If False, emit coloured key=value lines (for development).
        log_third_party_level: Log level for noisy third-party libraries.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    tp_level = getattr(logging, log_third_party_level.upper(), logging.WARNING)

    # ── Shared processors (run for both structlog and stdlib loggers) ──
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_context_vars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty(),
        )

    # ── Configure structlog ──────────────────────────────────────────
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── Configure stdlib logging (captures third-party logs too) ─────
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *shared_processors,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers
    for name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "chromadb",
        "sqlalchemy.engine",
        "sentence_transformers",
        "openai",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(tp_level)

    # App loggers at requested level
    logging.getLogger("app").setLevel(level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger.

    Drop-in replacement for ``logging.getLogger(__name__)``.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A structlog BoundLogger that supports key=value structured logging.
    """
    return structlog.get_logger(name)

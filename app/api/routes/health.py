"""Health check endpoints."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

_HEALTH_CACHE_TTL = 30  # seconds
_health_cache: dict | None = None
_health_cache_ts: float = 0.0
_health_cache_lock = threading.Lock()


def _check_database(settings: Settings) -> dict:
    """Lightweight database connectivity check."""
    from app.db.session import get_session_manager

    try:
        manager = get_session_manager()
        with manager.session_scope() as session:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok", "message": "Connected"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _check_vector_store(settings: Settings) -> dict:
    """Lightweight vector store connectivity check using singleton."""
    from app.api.dependencies import _get_vector_store

    try:
        vector_store = _get_vector_store()
        count = vector_store.collection.count()
        return {"status": "ok", "message": f"Connected, {count} vectors"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _check_embedding_service(settings: Settings) -> dict:
    """Check embedding service is configured using singleton (no test embedding call)."""
    from app.api.dependencies import _get_embedding_service

    try:
        service = _get_embedding_service()
        return {"status": "ok", "provider": service.provider}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _build_health_response(settings: Settings) -> dict:
    """Build health response with all service checks."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {},
    }

    checks["services"]["database"] = _check_database(settings)
    checks["services"]["vector_store"] = _check_vector_store(settings)
    checks["services"]["embedding_service"] = _check_embedding_service(settings)

    for svc in checks["services"].values():
        if svc.get("status") == "error":
            checks["status"] = "degraded"
            break

    return checks


@router.get("/")
async def health_check(settings: Settings = Depends(get_settings)) -> dict:
    """Health check endpoint with short-TTL caching to avoid repeated expensive checks."""
    global _health_cache, _health_cache_ts

    now = time.monotonic()
    if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        return _health_cache

    checks = await asyncio.to_thread(_build_health_cached, settings)

    if checks["status"] != "healthy":
        raise HTTPException(status_code=503, detail=checks)

    return checks


def _build_health_cached(settings: Settings) -> dict:
    """Build health response with thread-safe caching."""
    global _health_cache, _health_cache_ts

    with _health_cache_lock:
        now = time.monotonic()
        if _health_cache is not None and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
            return _health_cache

        checks = _build_health_response(settings)
        _health_cache = checks
        _health_cache_ts = time.monotonic()

    return checks


@router.get("/ready")
async def readiness_check(settings: Settings = Depends(get_settings)) -> dict:
    """Readiness check — lightweight DB ping only (no test embeddings)."""
    try:
        result = await asyncio.to_thread(_check_database, settings)
        if result["status"] != "ok":
            raise HTTPException(
                status_code=503, detail={"ready": False, "error": result["message"]}
            )
        return {"ready": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("health.readiness_failed", error=str(exc))
        raise HTTPException(status_code=503, detail={"ready": False, "error": str(exc)})

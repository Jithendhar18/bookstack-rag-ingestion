"""V1 metrics endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.observability import get_metrics
from app.api.schemas.v1 import MetricSnapshot, MetricsResponse
from app.config.logging import get_logger
from app.db.models import IngestionRun, QueryCache
from app.infrastructure.database.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_all_metrics() -> MetricsResponse:
    """Return all collected performance metrics."""
    perf = get_metrics()
    raw = perf.get_stats()
    snapshots = {
        name: MetricSnapshot(**vals) for name, vals in raw.items()
    }
    return MetricsResponse(
        metrics=snapshots,
        collected_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/queries")
async def get_query_metrics() -> dict:
    """Return query-specific metrics."""
    perf = get_metrics()
    query_stats = perf.get_stats("query") or {}
    return {
        "query": query_stats,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ingestion")
async def get_ingestion_metrics(db: Session = Depends(get_db)) -> dict:
    """Return ingestion-specific metrics from DB + performance tracker."""
    perf = get_metrics()
    perf_stats = perf.get_stats("ingestion") or {}

    total = db.query(IngestionRun).count()
    completed = db.query(IngestionRun).filter_by(status="COMPLETED").count()
    failed = db.query(IngestionRun).filter_by(status="FAILED").count()
    running = db.query(IngestionRun).filter_by(status="STARTED").count()

    return {
        "total_runs": total,
        "completed_runs": completed,
        "failed_runs": failed,
        "running_runs": running,
        "performance": perf_stats,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

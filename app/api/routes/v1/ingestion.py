"""V1 ingestion endpoints — async background jobs + partial ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.pagination import paginated_response
from app.api.response_formatters import format_ingestion_run, format_page_audit
from app.api.schemas.v1 import (
    IngestionRunResponse,
    IngestionRunStatusResponse,
    IngestionStatsResponse,
    PageAuditResponse,
    StartIngestionRequest,
)
from app.api.utils import generate_request_id
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.ingestion.ingestion_manager import IngestionManager
from app.pipelines.ingestion_pipeline import IngestionPipeline

logger = get_logger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _get_manager(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IngestionManager:
    pipeline = IngestionPipeline(settings=settings)
    return IngestionManager(session=db, ingestion_pipeline=pipeline, settings=settings)


# ── endpoints ──────────────────────────────────────────────────────

@router.post("/run", response_model=IngestionRunResponse)
async def start_ingestion(
    request: StartIngestionRequest,
    manager: IngestionManager = Depends(_get_manager),
):
    """Start an ingestion run (always async — returns immediately)."""
    request_id = generate_request_id()
    logger.info(
        "ingestion.start_request",
        request_id=request_id,
        full_sync=request.full_sync,
        page_ids=request.page_ids,
        force=request.force,
    )

    try:
        # Always run async to avoid blocking
        run = manager.start_ingestion(full_sync=request.full_sync, run_async=True)
        return IngestionRunResponse(**format_ingestion_run(run))
    except Exception as exc:
        logger.error("ingestion.start_failed", request_id=request_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start ingestion")


@router.get("/run/{run_id}/status", response_model=IngestionRunStatusResponse)
async def get_run_status(
    run_id: int,
    manager: IngestionManager = Depends(_get_manager),
):
    """Lightweight status poll for a running ingestion."""
    run = manager.get_ingestion_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")

    return IngestionRunStatusResponse(
        run_id=run.run_id,
        status=run.status,
        processed_pages=run.processed_pages,
        failed_pages=run.failed_pages,
    )


@router.get("/runs")
async def list_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    status: str | None = Query(None),
    manager: IngestionManager = Depends(_get_manager),
):
    """List ingestion runs with page-based pagination."""
    offset = (page - 1) * limit
    runs, total = manager.list_ingestion_runs(limit=limit, offset=offset, status=status)
    items = [IngestionRunResponse(**format_ingestion_run(r)) for r in runs]
    return paginated_response(items=items, total=total, page=page, limit=limit)


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
async def get_run(
    run_id: int,
    manager: IngestionManager = Depends(_get_manager),
):
    """Get full details of a specific ingestion run."""
    run = manager.get_ingestion_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")
    return IngestionRunResponse(**format_ingestion_run(run))


@router.get("/audit/page/{page_id}", response_model=list[PageAuditResponse])
async def page_audit(
    page_id: int,
    manager: IngestionManager = Depends(_get_manager),
):
    """Audit history for a specific page."""
    audits = manager.get_page_audit(page_id)
    return [PageAuditResponse(**format_page_audit(a)) for a in audits]


@router.get("/audit/run/{run_id}", response_model=list[PageAuditResponse])
async def run_audit(
    run_id: int,
    manager: IngestionManager = Depends(_get_manager),
):
    """All audit records for an ingestion run."""
    run = manager.get_ingestion_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")
    audits = manager.get_run_audit(run_id)
    return [PageAuditResponse(**format_page_audit(a)) for a in audits]


@router.get("/stats", response_model=IngestionStatsResponse)
async def ingestion_stats(
    manager: IngestionManager = Depends(_get_manager),
):
    """Summary statistics for all ingestion runs."""
    stats = manager.get_ingestion_stats()
    return IngestionStatsResponse(**stats)

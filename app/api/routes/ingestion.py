"""Ingestion control API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.response_formatters import format_ingestion_run, format_page_audit
from app.api.utils import generate_request_id
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.ingestion.ingestion_manager import IngestionManager
from app.pipelines.ingestion_pipeline import IngestionPipeline

logger = get_logger(__name__)
router = APIRouter(prefix="/ingestion", tags=["ingestion"])


# Dependency: Get ingestion manager
def get_ingestion_manager(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IngestionManager:
    """Get ingestion manager instance."""
    pipeline = IngestionPipeline(settings=settings)
    return IngestionManager(session=db, ingestion_pipeline=pipeline, settings=settings)


# Request/Response Models
class StartIngestionRequest(BaseModel):
    """Request to start ingestion."""

    full_sync: bool = Field(default=False, description="Perform full sync instead of incremental")
    run_async: bool = Field(default=True, description="Run asynchronously in background")


class IngestionRunResponse(BaseModel):
    """Ingestion run details."""

    run_id: int
    status: str
    started_at: str
    finished_at: str | None = None
    processed_pages: int
    failed_pages: int
    notes: str | None = None

    class Config:
        from_attributes = True


class PageAuditResponse(BaseModel):
    """Page sync audit record."""

    audit_id: int
    page_id: int | None
    status: str
    reason: str
    source_updated_at: str | None = None
    local_updated_at: str | None = None
    created_at: str

    class Config:
        from_attributes = True


class IngestionStatsResponse(BaseModel):
    """Overall ingestion statistics."""

    total_runs: int
    completed_runs: int
    failed_runs: int
    running_runs: int
    latest_run_id: int | None = None
    latest_run_status: str | None = None
    latest_run_at: str | None = None


# Endpoints
@router.post("/run", response_model=IngestionRunResponse)
async def start_ingestion(
    request: StartIngestionRequest,
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """Start an ingestion run.

    Args:
        request: Ingestion request parameters
        manager: Ingestion manager instance

    Returns:
        IngestionRunResponse with run_id and status
    """
    request_id = generate_request_id()
    logger.info("ingestion.start_request", request_id=request_id, full_sync=request.full_sync)

    try:
        run = manager.start_ingestion(full_sync=request.full_sync, run_async=request.run_async)
        return IngestionRunResponse(**format_ingestion_run(run))
    except Exception as e:
        logger.error("ingestion.start_failed", request_id=request_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start ingestion: {str(e)}")


@router.get("/runs", response_model=list[IngestionRunResponse])
async def list_ingestion_runs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Filter by status (STARTED, COMPLETED, FAILED)"),
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """List ingestion runs with pagination.

    Args:
        limit: Results per page
        offset: Page offset
        status: Optional status filter
        manager: Ingestion manager instance

    Returns:
        List of IngestionRunResponse
    """
    runs, total = manager.list_ingestion_runs(
        limit=limit,
        offset=offset,
        status=status,
    )

    return [IngestionRunResponse(**format_ingestion_run(run)) for run in runs]


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
async def get_ingestion_run(
    run_id: int,
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """Get details of a specific ingestion run.

    Args:
        run_id: Ingestion run ID
        manager: Ingestion manager instance

    Returns:
        IngestionRunResponse with details

    Raises:
        HTTPException: 404 if run not found
    """
    run = manager.get_ingestion_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")

    return IngestionRunResponse(**format_ingestion_run(run))


@router.get("/audit/page/{page_id}", response_model=list[PageAuditResponse])
async def get_page_audit(
    page_id: int,
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """Get audit history for a specific page.

    Args:
        page_id: BookStack page ID
        manager: Ingestion manager instance

    Returns:
        List of PageAuditResponse records sorted by date (newest first)
    """
    audits = manager.get_page_audit(page_id)
    return [PageAuditResponse(**format_page_audit(audit)) for audit in audits]


@router.get("/audit/run/{run_id}", response_model=list[PageAuditResponse])
async def get_run_audit(
    run_id: int,
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """Get all audit records for an ingestion run.

    Args:
        run_id: Ingestion run ID
        manager: Ingestion manager instance

    Returns:
        List of PageAuditResponse records
    """
    # Verify run exists
    run = manager.get_ingestion_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Ingestion run {run_id} not found")

    audits = manager.get_run_audit(run_id)
    return [PageAuditResponse(**format_page_audit(audit)) for audit in audits]


@router.get("/stats", response_model=IngestionStatsResponse)
async def get_ingestion_stats(
    manager: IngestionManager = Depends(get_ingestion_manager),
):
    """Get overall ingestion statistics.

    Args:
        manager: Ingestion manager instance

    Returns:
        IngestionStatsResponse with summary statistics
    """
    stats = manager.get_ingestion_stats()
    return IngestionStatsResponse(**stats)

"""Ingestion management service."""

from datetime import datetime, timezone
from threading import Thread
from typing import Optional

from sqlalchemy.orm import Session

from app.config.logging import get_logger
from app.config.settings import Settings
from app.db.models import IngestionRun, PageSyncAudit
from app.pipelines.ingestion_pipeline import IngestionPipeline

logger = get_logger(__name__)


class IngestionManager:
    """Manages ingestion pipeline execution and tracking."""

    def __init__(
        self,
        session: Session,
        ingestion_pipeline: IngestionPipeline,
        settings: Settings,
    ):
        """Initialize ingestion manager.

        Args:
            session: SQLAlchemy database session
            ingestion_pipeline: Pipeline instance
            settings: Application settings
        """
        self.session = session
        self.pipeline = ingestion_pipeline
        self.settings = settings

    def start_ingestion(
        self,
        full_sync: bool = False,
        run_async: bool = True,
    ) -> IngestionRun:
        """Start an ingestion run.

        Args:
            full_sync: Whether to do a full sync (vs. incremental)
            run_async: Whether to run asynchronously in background

        Returns:
            IngestionRun object
        """
        # Create ingestion run record
        run = IngestionRun(
            status="STARTED",
            processed_pages=0,
            failed_pages=0,
            notes=f"{'Full' if full_sync else 'Incremental'} sync started at {datetime.now(timezone.utc)}",
        )
        self.session.add(run)
        self.session.commit()
        logger.info("ingestion.run_created", run_id=run.run_id)

        # Execute pipeline
        if run_async:
            thread = Thread(
                target=self._run_ingestion,
                args=(run.run_id, full_sync),
                daemon=False,
                name=f"ingestion-run-{run.run_id}",
            )
            thread.start()
            logger.info("ingestion.async_started", run_id=run.run_id)
        else:
            self._run_ingestion(run.run_id, full_sync)
            logger.info("ingestion.sync_completed", run_id=run.run_id)

        return run

    def _run_ingestion(self, run_id: int, full_sync: bool) -> None:
        """Execute ingestion pipeline.

        Creates its own database session for thread-safety.

        Args:
            run_id: Ingestion run ID
            full_sync: Whether to do full sync
        """
        from app.db.session import get_session_manager

        manager = get_session_manager()
        with manager.session_scope() as thread_session:
            run = thread_session.query(IngestionRun).filter_by(run_id=run_id).first()
            if not run:
                logger.error("ingestion.run_not_found", run_id=run_id)
                return

            try:
                logger.info("ingestion.pipeline_starting", run_id=run_id)

                # Run pipeline
                self.pipeline.run()

                # Update run with results from pipeline metrics
                run.status = "COMPLETED"
                run.processed_pages = self.pipeline.metrics.get("processed_pages", 0)
                run.failed_pages = self.pipeline.metrics.get("failed_pages", 0)
                run.finished_at = datetime.now(timezone.utc)
                run.notes = f"Processed {run.processed_pages} pages, {run.failed_pages} failures"
                thread_session.commit()

                logger.info(
                    "ingestion.run_completed",
                    run_id=run_id,
                    processed=run.processed_pages,
                    failed=run.failed_pages,
                )

            except Exception as e:
                logger.error("ingestion.run_failed", run_id=run_id, error=str(e), exc_info=True)
                run.status = "FAILED"
                run.finished_at = datetime.now(timezone.utc)
                run.notes = f"Error: {str(e)}"
                thread_session.commit()

    def get_ingestion_run(self, run_id: int) -> Optional[IngestionRun]:
        """Get ingestion run details.

        Args:
            run_id: Ingestion run ID

        Returns:
            IngestionRun or None
        """
        return self.session.query(IngestionRun).filter_by(run_id=run_id).first()

    def list_ingestion_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> tuple[list[IngestionRun], int]:
        """List ingestion runs with pagination.

        Args:
            limit: Number of runs per page
            offset: Page offset
            status: Optional status filter

        Returns:
            Tuple of (runs list, total count)
        """
        query = self.session.query(IngestionRun)
        if status:
            query = query.filter_by(status=status)

        total = query.count()
        runs = query.order_by(IngestionRun.started_at.desc()).offset(offset).limit(limit).all()

        return runs, total

    def get_page_audit(self, page_id: int) -> list[PageSyncAudit]:
        """Get audit history for a specific page.

        Args:
            page_id: BookStack page ID

        Returns:
            List of audit records sorted by date
        """
        return (
            self.session.query(PageSyncAudit)
            .filter_by(page_id=page_id)
            .order_by(PageSyncAudit.created_at.desc())
            .all()
        )

    def get_run_audit(self, run_id: int) -> list[PageSyncAudit]:
        """Get all audit records for an ingestion run.

        Args:
            run_id: Ingestion run ID

        Returns:
            List of audit records
        """
        return (
            self.session.query(PageSyncAudit)
            .filter_by(run_id=run_id)
            .order_by(PageSyncAudit.created_at.desc())
            .all()
        )

    def get_ingestion_stats(self) -> dict:
        """Get overall ingestion statistics.

        Returns:
            Dictionary with stats
        """
        total_runs = self.session.query(IngestionRun).count()
        completed_runs = self.session.query(IngestionRun).filter_by(status="COMPLETED").count()
        failed_runs = self.session.query(IngestionRun).filter_by(status="FAILED").count()
        running_runs = self.session.query(IngestionRun).filter_by(status="STARTED").count()

        # Get latest run
        latest_run = (
            self.session.query(IngestionRun).order_by(IngestionRun.started_at.desc()).first()
        )

        return {
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "running_runs": running_runs,
            "latest_run_id": latest_run.run_id if latest_run else None,
            "latest_run_status": latest_run.status if latest_run else None,
            "latest_run_at": latest_run.started_at.isoformat() if latest_run else None,
        }

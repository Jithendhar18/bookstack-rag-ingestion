from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from app.analyzers.structure_analyzer import DocumentStructure, StructureAnalyzer
from app.chunking.chunking_engine import ChunkingEngine, TextChunk
from app.clients.bookstack_client import BookStackClient
from app.config.logging import get_logger, run_id_ctx
from app.config.settings import Settings
from app.db.metadata_store import MetadataStore
from app.db.migration_runner import MigrationRunner
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService
from app.loaders.document_loader import DocumentLoader, LoadedDocument
from app.metadata.metadata_enricher import EnrichedChunk, MetadataEnricher
from app.parsers.content_parser import ContentParser
from app.sync.document_sync_service import DocumentSyncService

logger = get_logger(__name__)


class IngestionPipeline:
    """End-to-end pipeline for ingesting BookStack pages into the vector store."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.bookstack_client = BookStackClient(settings=settings)
        self.metadata_store = MetadataStore(settings=settings)
        self.vector_store = VectorStore(settings=settings)

        self.sync_service = DocumentSyncService(
            bookstack_client=self.bookstack_client,
            metadata_store=self.metadata_store,
        )

        self.loader = DocumentLoader(bookstack_client=self.bookstack_client, settings=settings)
        self.parser = ContentParser()
        self.structure_analyzer = StructureAnalyzer(parser=self.parser)
        self.chunking_engine = ChunkingEngine(
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
        self.metadata_enricher = MetadataEnricher()
        self.embedding_service = EmbeddingService(settings=settings)

        # Performance metrics
        self.metrics = {
            "total_pages": 0,
            "processed_pages": 0,
            "failed_pages": 0,
            "total_chunks": 0,
            "total_embeddings": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "start_time": None,
            "end_time": None,
        }

    def run(self) -> None:
        """Run the complete ingestion pipeline."""
        self.metrics["start_time"] = time.time()

        applied_migrations = MigrationRunner(settings=self.settings).bootstrap_if_uninitialized()
        if applied_migrations:
            logger.info("schema.bootstrapped", migration_count=len(applied_migrations))

        run_id = self.metadata_store.start_ingestion_run(notes="bookstack_ingestion")
        run_id_ctx.set(run_id)
        processed_pages = 0
        failed_pages = 0

        try:
            pages = self.bookstack_client.get_pages()
            logger.info("pages.fetched", count=len(pages))
            self.metrics["total_pages"] = len(pages)

            remote_page_ids = self.sync_service.extract_page_ids(pages)
            local_page_ids = self.metadata_store.list_document_page_ids()

            deleted_page_ids = sorted(local_page_ids - remote_page_ids)
            if deleted_page_ids:
                logger.info("pages.deleted_found", count=len(deleted_page_ids))
                for page_id in deleted_page_ids:
                    self._purge_deleted_page(run_id=run_id, page_id=page_id)

            pages_to_sync, decisions = self.sync_service.classify_pages(pages=pages)
            for decision in decisions:
                if decision.status == "UNCHANGED":
                    self.metadata_store.record_page_audit(
                        run_id=run_id,
                        page_id=decision.page_id,
                        status=decision.status,
                        reason=decision.reason,
                        source_updated_at=decision.source_updated_at,
                        local_updated_at=decision.local_updated_at,
                    )

            if not pages_to_sync:
                logger.info("ingestion.up_to_date")
                self.metadata_store.finish_ingestion_run(
                    run_id=run_id,
                    status="SUCCESS",
                    processed_pages=processed_pages,
                    failed_pages=failed_pages,
                    notes="no_new_or_updated_pages",
                )
                self._log_completion_metrics()
                return

            logger.info("pages.to_ingest", count=len(pages_to_sync))

            decision_by_page_id = {decision.page_id: decision for decision in decisions}
            batches = self.sync_service.as_batches(
                pages_to_sync, batch_size=self.settings.sync_batch_size
            )

            for batch_index, batch in enumerate(batches, start=1):
                logger.info(
                    "batch.processing",
                    batch=batch_index,
                    total_batches=len(batches),
                    pages=len(batch),
                )

                if self.settings.enable_parallel_processing and len(batch) > 1:
                    processed, failed = self._process_batch_parallel(
                        batch, run_id, decision_by_page_id
                    )
                    processed_pages += processed
                    failed_pages += failed
                else:
                    for page in batch:
                        page_id = int(page["id"])
                        decision = decision_by_page_id.get(page_id)

                        try:
                            if self._process_page_with_lock(page_id, run_id, decision):
                                processed_pages += 1
                        except Exception as exc:  # noqa: BLE001
                            failed_pages += 1
                            logger.error("page.failed", page_id=page_id, error=str(exc))

            run_status = "SUCCESS" if failed_pages == 0 else "PARTIAL_SUCCESS"
            self.metadata_store.finish_ingestion_run(
                run_id=run_id,
                status=run_status,
                processed_pages=processed_pages,
                failed_pages=failed_pages,
                notes=None,
            )
            logger.info(
                "ingestion.complete",
                status=run_status,
                processed=processed_pages,
                failed=failed_pages,
            )
            self._log_completion_metrics()

        except Exception as exc:  # noqa: BLE001 - top-level run failure should be audited
            self.metadata_store.finish_ingestion_run(
                run_id=run_id,
                status="FAILED",
                processed_pages=processed_pages,
                failed_pages=failed_pages,
                notes=f"pipeline_failed:{exc.__class__.__name__}",
            )
            logger.error("pipeline.failed", error=str(exc), exc_info=True)
            raise

    def _process_batch_parallel(
        self, batch: list, run_id: int, decision_by_page_id: dict
    ) -> tuple[int, int]:
        """Process batch of pages in parallel."""
        processed = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            futures = {}
            for page in batch:
                page_id = int(page["id"])
                decision = decision_by_page_id.get(page_id)
                future = executor.submit(
                    self._process_page_with_lock,
                    page_id,
                    run_id,
                    decision,
                )
                futures[future] = page_id

            for future in as_completed(futures):
                page_id = futures[future]
                try:
                    if future.result():
                        processed += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    logger.error("page.failed", page_id=page_id, error=str(exc))

        return processed, failed

    def _process_page_with_lock(
        self, page_id: int, run_id: int, decision: Optional[object]
    ) -> bool:
        """
        Process a single page with advisory lock.

        Returns True if successful, False otherwise.
        """
        with self.metadata_store.acquire_page_lock(page_id) as acquired:
            if not acquired:
                self.metadata_store.record_page_audit(
                    run_id=run_id,
                    page_id=page_id,
                    status="SKIPPED_LOCKED",
                    reason="advisory_lock_not_acquired",
                    source_updated_at=decision.source_updated_at if decision else None,  # type: ignore
                    local_updated_at=decision.local_updated_at if decision else None,  # type: ignore
                )
                logger.debug("page.skipped_locked", page_id=page_id)
                return False

            logger.info("page.processing", page_id=page_id)
            try:
                page_start = time.time()
                self._process_page(page_id)
                page_duration = time.time() - page_start

                self.metrics["processed_pages"] += 1
                self.metadata_store.record_page_audit(
                    run_id=run_id,
                    page_id=page_id,
                    status=decision.status if decision else "UPDATED",  # type: ignore
                    reason="processed_successfully",
                    source_updated_at=decision.source_updated_at if decision else None,  # type: ignore
                    local_updated_at=decision.local_updated_at if decision else None,  # type: ignore
                )
                logger.info("page.processed", page_id=page_id, duration_s=round(page_duration, 2))
                return True

            except Exception as exc:  # noqa: BLE001 - keep pipeline resilient per page
                self.metrics["failed_pages"] += 1
                self.metadata_store.record_page_audit(
                    run_id=run_id,
                    page_id=page_id,
                    status="FAILED",
                    reason=f"processing_error:{exc.__class__.__name__}",
                    source_updated_at=decision.source_updated_at if decision else None,  # type: ignore
                    local_updated_at=decision.local_updated_at if decision else None,  # type: ignore
                )
                logger.error("page.failed", page_id=page_id, error=str(exc))
                return False

    def _purge_deleted_page(self, run_id: int, page_id: int) -> None:
        with self.metadata_store.acquire_page_lock(page_id) as acquired:
            if not acquired:
                self.metadata_store.record_page_audit(
                    run_id=run_id,
                    page_id=page_id,
                    status="SKIPPED_LOCKED",
                    reason="advisory_lock_not_acquired_during_purge",
                )
                logger.debug("page.purge_skipped_locked", page_id=page_id)
                return

            self.vector_store.delete_page_chunks(page_id=page_id)
            self.metadata_store.delete_document(page_id=page_id)
            self.metadata_store.record_page_audit(
                run_id=run_id,
                page_id=page_id,
                status="DELETED",
                reason="missing_in_remote_bookstack_pages",
            )
            logger.info("page.purged", page_id=page_id)

    def _process_page(self, page_id: int) -> None:
        """Process a single page through the entire pipeline."""
        document = self.loader.load_page(page_id)
        plain_text = self._parse_content(document)

        structure = self.structure_analyzer.analyze(
            title=document.title,
            markdown_content=document.markdown,
            plain_text=plain_text,
        )

        chunks, section_chunk_counts = self._generate_chunks(structure)
        if not chunks:
            logger.warning("page.no_content", page_id=page_id)
            return

        logger.debug("page.chunks_generated", page_id=page_id, count=len(chunks))
        self.metrics["total_chunks"] += len(chunks)

        enriched_chunks = self._enrich_chunks(document, structure, chunks, section_chunk_counts)
        self._sync_chunks(page_id, document, enriched_chunks)

    def _parse_content(self, document: LoadedDocument) -> str:
        """Parse document content to plain text."""
        if document.markdown.strip():
            return self.parser.parse_markdown(document.markdown)
        return self.parser.parse_html(document.markdown)

    def _generate_chunks(self, structure: DocumentStructure) -> tuple[list[TextChunk], list[int]]:
        """Generate text chunks from document sections, falling back to full text.

        Returns:
            Tuple of (chunks, section_chunk_counts) where section_chunk_counts[i]
            is the number of chunks produced from sections[i].
        """
        chunks: list[TextChunk] = []
        section_chunk_counts: list[int] = []
        global_chunk_index = 0

        for section in structure.sections:
            section_chunks = self.chunking_engine.chunk_text(section.content)
            section_chunk_counts.append(len(section_chunks))
            for section_chunk in section_chunks:
                chunks.append(
                    TextChunk(
                        chunk_index=global_chunk_index,
                        text=section_chunk.text,
                        start_token=section_chunk.start_token,
                        end_token=section_chunk.end_token,
                    )
                )
                global_chunk_index += 1

        if not chunks:
            chunks = self.chunking_engine.chunk_text(structure.full_text)
            section_chunk_counts = []

        return chunks, section_chunk_counts

    def _enrich_chunks(
        self,
        document: LoadedDocument,
        structure: DocumentStructure,
        chunks: list[TextChunk],
        section_chunk_counts: list[int],
    ) -> list[EnrichedChunk]:
        """Enrich chunks with section metadata, falling back to flat enrichment."""
        enriched_chunks: list[EnrichedChunk] = []

        # Map each chunk to its originating section using pre-computed counts
        chunk_offset = 0
        for idx, section in enumerate(structure.sections):
            if idx >= len(section_chunk_counts):
                break
            count = section_chunk_counts[idx]
            section_chunks = chunks[chunk_offset : chunk_offset + count]
            chunk_offset += count

            if section_chunks:
                enriched = self.metadata_enricher.enrich(
                    document=document,
                    chunks=section_chunks,
                    section_path=section.heading_path,
                    section_level=section.level,
                )
                enriched_chunks.extend(enriched)

        # Fallback if no hierarchical enrichment matched
        if not enriched_chunks:
            enriched_chunks = self.metadata_enricher.enrich(
                document=document,
                chunks=chunks,
            )

        return enriched_chunks

    def _sync_chunks(
        self,
        page_id: int,
        document: LoadedDocument,
        enriched_chunks: list[EnrichedChunk],
    ) -> None:
        """Diff enriched chunks against stored chunks and sync changes."""
        existing_chunks = self.metadata_store.get_document_chunks(page_id=page_id)

        existing_chunk_ids = set(existing_chunks.keys())
        desired_chunk_ids = {chunk.chunk_id for chunk in enriched_chunks}

        chunk_ids_to_delete = sorted(existing_chunk_ids - desired_chunk_ids)
        if chunk_ids_to_delete:
            logger.debug("chunks.deleting_outdated", count=len(chunk_ids_to_delete))
            self.vector_store.delete_chunks_by_ids(chunk_ids_to_delete)
            self.metadata_store.delete_document_chunks_by_vector_ids(
                page_id=page_id, vector_ids=chunk_ids_to_delete
            )

        chunks_to_upsert = [
            chunk
            for chunk in enriched_chunks
            if chunk.chunk_id not in existing_chunks
            or str(existing_chunks[chunk.chunk_id]["chunk_text"]) != chunk.chunk_text
        ]

        vector_ids: list[str] = []
        if chunks_to_upsert:
            logger.debug("chunks.upserting", count=len(chunks_to_upsert))
            chunk_texts = [chunk.chunk_text for chunk in chunks_to_upsert]
            embeddings = self.embedding_service.embed_batch(chunk_texts)
            self.metrics["total_embeddings"] += len(embeddings)

            vector_ids = self.vector_store.upsert_chunks(
                chunks=chunks_to_upsert, embeddings=embeddings
            )

        self.metadata_store.upsert_document(document=document)

        if vector_ids:
            chunk_rows = [
                (chunk.metadata.chunk_index, chunk.chunk_text, vector_ids[idx])
                for idx, chunk in enumerate(chunks_to_upsert)
            ]
            self.metadata_store.upsert_document_chunks(page_id=page_id, rows=chunk_rows)

        if not chunk_ids_to_delete and not chunks_to_upsert:
            logger.debug("page.no_chunk_changes", page_id=page_id)

    def _log_completion_metrics(self) -> None:
        """Log performance and completion metrics."""
        self.metrics["end_time"] = time.time()
        duration = self.metrics["end_time"] - self.metrics["start_time"]

        logger.info(
            "pipeline.metrics",
            total_pages=self.metrics["total_pages"],
            processed_pages=self.metrics["processed_pages"],
            failed_pages=self.metrics["failed_pages"],
            total_chunks=self.metrics["total_chunks"],
            total_embeddings=self.metrics["total_embeddings"],
            duration_s=round(duration, 2),
            avg_page_s=round(duration / max(1, self.metrics["processed_pages"]), 2),
        )

        cache_stats = self.embedding_service.get_cache_stats()
        if cache_stats:
            logger.info("embedding_cache.stats", **cache_stats)

from __future__ import annotations

from app.analyzers.structure_analyzer import StructureAnalyzer
from app.chunking.chunking_engine import ChunkingEngine, TextChunk
from app.clients.bookstack_client import BookStackClient
from app.config.settings import Settings
from app.db.migration_runner import MigrationRunner
from app.db.metadata_store import MetadataStore
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService
from app.loaders.document_loader import DocumentLoader
from app.metadata.metadata_enricher import MetadataEnricher
from app.parsers.content_parser import ContentParser
from app.sync.document_sync_service import DocumentSyncService


class IngestionPipeline:
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

    def run(self) -> None:
        applied_migrations = MigrationRunner(settings=self.settings).run()
        if applied_migrations:
            print(f"Applied {len(applied_migrations)} migration(s) before ingestion.")

        run_id = self.metadata_store.start_ingestion_run(notes="bookstack_ingestion")
        processed_pages = 0
        failed_pages = 0

        try:
            pages = self.bookstack_client.get_pages()
            remote_page_ids = self.sync_service.extract_page_ids(pages)
            local_page_ids = self.metadata_store.list_document_page_ids()

            deleted_page_ids = sorted(local_page_ids - remote_page_ids)
            if deleted_page_ids:
                print(f"Found {len(deleted_page_ids)} deleted page(s) to purge.")
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
                print("No new or updated pages found. Ingestion is up to date.")
                self.metadata_store.finish_ingestion_run(
                    run_id=run_id,
                    status="SUCCESS",
                    processed_pages=processed_pages,
                    failed_pages=failed_pages,
                    notes="no_new_or_updated_pages",
                )
                return

            print(f"Found {len(pages_to_sync)} page(s) to ingest.")

            decision_by_page_id = {decision.page_id: decision for decision in decisions}
            batches = self.sync_service.as_batches(pages_to_sync, batch_size=self.settings.sync_batch_size)
            for batch_index, batch in enumerate(batches, start=1):
                print(f"Processing batch {batch_index}/{len(batches)} ({len(batch)} page(s))")
                for page in batch:
                    page_id = int(page["id"])
                    decision = decision_by_page_id.get(page_id)

                    with self.metadata_store.acquire_page_lock(page_id) as acquired:
                        if not acquired:
                            self.metadata_store.record_page_audit(
                                run_id=run_id,
                                page_id=page_id,
                                status="SKIPPED_LOCKED",
                                reason="advisory_lock_not_acquired",
                                source_updated_at=decision.source_updated_at if decision else None,
                                local_updated_at=decision.local_updated_at if decision else None,
                            )
                            print(f"Skipping page_id={page_id}: already locked by another worker.")
                            continue

                        print(f"Processing page_id={page_id}")
                        try:
                            self._process_page(page_id)
                            processed_pages += 1
                            self.metadata_store.record_page_audit(
                                run_id=run_id,
                                page_id=page_id,
                                status=decision.status if decision else "UPDATED",
                                reason="processed_successfully",
                                source_updated_at=decision.source_updated_at if decision else None,
                                local_updated_at=decision.local_updated_at if decision else None,
                            )
                        except Exception as exc:  # noqa: BLE001 - keep pipeline resilient per page
                            failed_pages += 1
                            self.metadata_store.record_page_audit(
                                run_id=run_id,
                                page_id=page_id,
                                status="FAILED",
                                reason=f"processing_error:{exc.__class__.__name__}",
                                source_updated_at=decision.source_updated_at if decision else None,
                                local_updated_at=decision.local_updated_at if decision else None,
                            )
                            print(f"Failed page_id={page_id}: {exc}")

            run_status = "SUCCESS" if failed_pages == 0 else "PARTIAL_SUCCESS"
            self.metadata_store.finish_ingestion_run(
                run_id=run_id,
                status=run_status,
                processed_pages=processed_pages,
                failed_pages=failed_pages,
                notes=None,
            )
            print("Ingestion complete.")
        except Exception as exc:  # noqa: BLE001 - top-level run failure should be audited
            self.metadata_store.finish_ingestion_run(
                run_id=run_id,
                status="FAILED",
                processed_pages=processed_pages,
                failed_pages=failed_pages,
                notes=f"pipeline_failed:{exc.__class__.__name__}",
            )
            raise

    def _purge_deleted_page(self, run_id: int, page_id: int) -> None:
        with self.metadata_store.acquire_page_lock(page_id) as acquired:
            if not acquired:
                self.metadata_store.record_page_audit(
                    run_id=run_id,
                    page_id=page_id,
                    status="SKIPPED_LOCKED",
                    reason="advisory_lock_not_acquired_during_purge",
                )
                print(f"Skipping purge for page_id={page_id}: already locked by another worker.")
                return

            self.vector_store.delete_page_chunks(page_id=page_id)
            self.metadata_store.delete_document(page_id=page_id)
            self.metadata_store.record_page_audit(
                run_id=run_id,
                page_id=page_id,
                status="DELETED",
                reason="missing_in_remote_bookstack_pages",
            )
            print(f"Purged deleted page_id={page_id} from vector and metadata stores.")

    def _process_page(self, page_id: int) -> None:
        document = self.loader.load_page(page_id)

        plain_text = self.parser.parse_markdown(document.markdown)
        structure = self.structure_analyzer.analyze(
            title=document.title,
            markdown_content=document.markdown,
            plain_text=plain_text,
        )

        chunks: list[TextChunk] = []
        global_chunk_index = 0

        for section in structure.sections:
            section_chunks = self.chunking_engine.chunk_text(section.content)
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

        if not chunks:
            print(f"Skipping page_id={page_id}: no content chunks generated.")
            return

        enriched_chunks = self.metadata_enricher.enrich(document=document, chunks=chunks)
        existing_chunks = self.metadata_store.get_document_chunks(page_id=page_id)

        desired_chunk_by_id = {chunk.chunk_id: chunk for chunk in enriched_chunks}
        existing_chunk_ids = set(existing_chunks.keys())
        desired_chunk_ids = set(desired_chunk_by_id.keys())

        chunk_ids_to_delete = sorted(existing_chunk_ids - desired_chunk_ids)
        if chunk_ids_to_delete:
            self.vector_store.delete_chunks_by_ids(chunk_ids_to_delete)
            self.metadata_store.delete_document_chunks_by_vector_ids(page_id=page_id, vector_ids=chunk_ids_to_delete)

        chunks_to_upsert = [
            chunk
            for chunk in enriched_chunks
            if chunk.chunk_id not in existing_chunks
            or str(existing_chunks[chunk.chunk_id]["chunk_text"]) != chunk.chunk_text
        ]

        vector_ids: list[str] = []
        if chunks_to_upsert:
            chunk_texts = [chunk.chunk_text for chunk in chunks_to_upsert]
            embeddings = self.embedding_service.embed_batch(chunk_texts)
            vector_ids = self.vector_store.upsert_chunks(chunks=chunks_to_upsert, embeddings=embeddings)

        self.metadata_store.upsert_document(document=document)

        if vector_ids:
            chunk_rows = []
            for idx, chunk in enumerate(chunks_to_upsert):
                chunk_rows.append((chunk.metadata.chunk_index, chunk.chunk_text, vector_ids[idx]))

            self.metadata_store.upsert_document_chunks(page_id=page_id, rows=chunk_rows)

        if not chunk_ids_to_delete and not chunks_to_upsert:
            print(f"page_id={page_id}: metadata updated, no chunk text changes detected.")

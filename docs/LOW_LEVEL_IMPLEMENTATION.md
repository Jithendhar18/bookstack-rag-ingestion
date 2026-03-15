# Low-Level Implementation Guide

This document explains the ingestion system internals, data flow, and operating model.

For architecture visuals and state diagrams, see [docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md](docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md).

## 1) Runtime Flow (Step-by-Step)

1. `scripts/run_ingestion.py` loads settings from `.env`.
2. `IngestionPipeline.run()` executes Alembic migrations to head.
3. BookStack pages are fetched (`GET /api/pages`).
4. Delete propagation runs:
   - local `documents.page_id` set
   - remote page id set
   - local-remote diff is purged from Chroma + PostgreSQL
5. Incremental candidate selection runs (`updated_at` compare).
6. Pages are processed in batches (`SYNC_BATCH_SIZE`).
7. Per-page advisory lock (`pg_try_advisory_lock`) prevents duplicate workers.
8. For each page:
   - full page content loaded (`GET /api/pages/{id}`)
   - markdown parsed to text
   - logical sections extracted
   - token chunks generated
   - chunk metadata enriched
9. Field-level chunk delta is computed against `document_chunks`:
   - deleted chunks -> removed from Chroma + PostgreSQL
   - changed/new chunks -> embedded + upserted
   - unchanged chunks -> untouched
10. `documents` row is upserted with latest source metadata.

## 2) Data Model

### documents

- `page_id` PK, source identity
- `title`, `book_slug`, `chapter_id`
- `updated_at` from BookStack
- `last_synced_at` local ingestion timestamp

### document_chunks

- `chunk_id` PK
- `page_id` FK -> documents
- `chunk_index` deterministic ordering
- `chunk_text` canonical chunk content
- `vector_id` deterministic id used in Chroma (`{page_id}:{chunk_index}`)
- `created_at`

### ingestion_runs

- `run_id` PK
- `started_at`, `finished_at`
- `status` (`RUNNING`, `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`)
- `processed_pages`, `failed_pages`
- `notes`

### page_sync_audit

- `audit_id` PK
- `run_id` FK -> ingestion_runs
- `page_id`
- `status` (`NEW`, `UPDATED`, `UNCHANGED`, `DELETED`, `SKIPPED_LOCKED`, `FAILED`)
- `reason`
- `source_updated_at`, `local_updated_at`
- `created_at`

## 3) ORM Layer

ORM stack uses SQLAlchemy 2.x:

- `app/db/base.py`: declarative base
- `app/db/models.py`: `Document`, `DocumentChunk`
- `app/db/session.py`: engine + session scope helper
- `app/db/metadata_store.py`: repository-style methods used by pipeline

Design notes:

- Session scope commits on success and rolls back on failure.
- Locking is done with SQL functions through SQLAlchemy `text()`.
- `expire_on_commit=False` avoids detached-refresh friction in service code.

## 4) Migration Strategy

- Alembic config: `alembic.ini`
- Environment: `db/alembic/env.py`
- Revisions: `db/alembic/versions/*`
- Applied version tracked in `alembic_version`

Pipeline calls migrations before ingestion to guarantee schema compatibility.

## 5) Chroma Semantics

- Collection: `bookstack_documents` (configurable)
- Upsert is id-based, so same chunk id overwrites prior vector/doc/metadata.
- Delete propagation and chunk-level delta call Chroma delete by page filter or explicit ids.

## 6) Reliability Controls

- BookStack HTTP retries for 429/5xx
- Configurable request rate limiting
- Embedding retry with exponential backoff
- Page-level advisory lock for idempotent multi-worker runs

## 7) Audit Trail Semantics

Each ingestion run writes one row to `ingestion_runs` and multiple rows to `page_sync_audit`.

Status mapping:

- `NEW`: page not present locally and selected for ingestion.
- `UPDATED`: page exists locally and source `updated_at` is newer.
- `UNCHANGED`: page exists locally and source `updated_at` is not newer.
- `DELETED`: page exists locally but not in current BookStack page list.
- `SKIPPED_LOCKED`: advisory lock could not be acquired.
- `FAILED`: page processing raised an exception.

## 8) Operational Commands

- Run compose infra:
  - `docker compose up -d`
- Run migrations:
  - `python3 scripts/db_migrate.py`
- Run ingestion:
  - `python3 scripts/run_ingestion.py`

## 9) Inspecting Audit Data

Example SQL queries:

```sql
-- Latest ingestion runs
SELECT run_id, started_at, finished_at, status, processed_pages, failed_pages, notes
FROM ingestion_runs
ORDER BY run_id DESC
LIMIT 20;

-- Page decisions for a specific run
SELECT run_id, page_id, status, reason, source_updated_at, local_updated_at, created_at
FROM page_sync_audit
WHERE run_id = :run_id
ORDER BY audit_id;

-- Decision breakdown over time
SELECT status, COUNT(*) AS total
FROM page_sync_audit
GROUP BY status
ORDER BY status;
```

## 10) Extensibility Points

- Replace embedding model/provider: `app/embeddings/embedding_service.py`
- Swap chunk strategy: `app/chunking/chunking_engine.py`
- Add richer section graph extraction: `app/analyzers/structure_analyzer.py`
- Add observability hooks around pipeline stage boundaries.

## 11) Debugging With Diagrams

Use the diagrams document as a triage map:

1. Start with the **Ingestion Sequence** diagram to locate the failing stage.
2. Use the **Page Decision State Model** to validate whether a page status is expected.
3. Use the **Chunk Delta Decision Logic** when chunk/vector counts are surprising.
4. Use the **Failure and Recovery Paths** diagram to map retries versus terminal failures.

## 12) Investigation Runbook

### A) Why was a page skipped?

Likely status: `SKIPPED_LOCKED`.

Check:

```sql
SELECT run_id, page_id, status, reason, created_at
FROM page_sync_audit
WHERE status = 'SKIPPED_LOCKED'
ORDER BY audit_id DESC
LIMIT 50;
```

If frequent, reduce worker concurrency or inspect long-running workers holding advisory locks.

### B) Why were vectors deleted?

Vectors are deleted in two cases:

- page removed from BookStack (`DELETED`)
- chunk removed during field-level delta reconciliation

Check deleted pages:

```sql
SELECT run_id, page_id, status, reason, created_at
FROM page_sync_audit
WHERE status = 'DELETED'
ORDER BY audit_id DESC
LIMIT 50;
```

Then compare `document_chunks` and Chroma collection counts for the same period.

### C) Why did run status become PARTIAL_SUCCESS?

At least one page failed while others succeeded.

Check:

```sql
SELECT run_id, status, processed_pages, failed_pages, notes, started_at, finished_at
FROM ingestion_runs
ORDER BY run_id DESC
LIMIT 20;

SELECT run_id, page_id, status, reason, created_at
FROM page_sync_audit
WHERE run_id = :run_id AND status = 'FAILED'
ORDER BY audit_id;
```

The `reason` field contains the exception class marker (for example, `processing_error:RuntimeError`).

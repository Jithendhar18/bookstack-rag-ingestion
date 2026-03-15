# BookStack RAG Ingestion

A production-style Python ingestion pipeline that syncs content from BookStack, transforms it into tokenized chunks, creates embeddings, and stores output in:

- ChromaDB (vector storage)
- PostgreSQL (relational metadata)

This project intentionally stops at ingestion. It does **not** implement the LLM query layer.

## Architecture

```text
BookStack API
  -> Document Sync Service
  -> Document Loader
  -> Content Parser
  -> Structure Analyzer
  -> Chunking Engine
  -> Metadata Enrichment
  -> Embedding Service
  -> Vector Database (Chroma)
  -> RDBMS Metadata Storage (PostgreSQL)
```

## Complete Picture (Analysis View)

The pipeline has four runtime phases:

1. **Bootstrap**: load settings, run Alembic migrations, create ingestion run audit row.
2. **Discovery & Classification**: fetch remote pages, detect source deletions, classify `NEW/UPDATED/UNCHANGED`.
3. **Per-Page Processing**: lock page, load content, parse/analyze/chunk, compute chunk delta.
4. **Persistence & Audit**: write vectors to Chroma, metadata to PostgreSQL, finalize run status.

Storage responsibility split:

- **Chroma**: embeddings and chunk documents for retrieval.
- **PostgreSQL**: source metadata, chunk text snapshots, run-level and page-level audit trail.

For visual flow and state-machine diagrams, see [docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md](docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md).

## Project Structure

```text
bookstack-rag-ingestion/
  app/
    config/
      settings.py
    clients/
      bookstack_client.py
    sync/
      document_sync_service.py
    loaders/
      document_loader.py
    parsers/
      content_parser.py
    analyzers/
      structure_analyzer.py
    chunking/
      chunking_engine.py
    metadata/
      metadata_enricher.py
    embeddings/
      embedding_service.py
    db/
      base.py
      models.py
      session.py
      README.md
      vector_store.py
      metadata_store.py
      migration_runner.py
    pipelines/
      ingestion_pipeline.py
  scripts/
    db_migrate.py
    run_ingestion.py
  db/
    alembic/
      env.py
      versions/
        20260315_0001_init_schema.py
  alembic.ini
  requirements.txt
  README.md
```

## Features Implemented

1. BookStack client with token auth (`get_pages`, `get_page`, plus helper endpoints)
2. Sync logic using `updated_at` to identify stale/new documents
3. Full document loading from page details
4. Markdown -> HTML -> plain text parsing
5. Structure analysis based on markdown headings
6. Token chunking using `tiktoken` (`chunk_size=500`, `overlap=100`)
7. Metadata enrichment per chunk
8. Embeddings using OpenAI (`text-embedding-3-large`) or local sentence-transformers
9. Vector upsert into Chroma collection `bookstack_documents`
10. Relational metadata persistence in PostgreSQL (`documents`, `document_chunks`)
11. SQLAlchemy ORM metadata store and session management
12. End-to-end ingestion pipeline + entry script
13. Incremental sync batching (`SYNC_BATCH_SIZE`)
14. BookStack API retries + rate limiting
15. Embedding retries with exponential backoff
16. PostgreSQL advisory locks for per-page idempotency
17. Delete propagation for pages removed from BookStack
18. Field-level delta on chunks (only changed/new chunks are re-embedded)
19. Ingestion audit trail (`ingestion_runs`, `page_sync_audit`)

## Requirements

- Python 3.11+
- Running PostgreSQL instance (or Docker Compose)
- Accessible BookStack API
- OpenAI API key

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in project root:

```env
BOOKSTACK_URL=https://your-bookstack.example.com
BOOKSTACK_TOKEN_ID=your_token_id
BOOKSTACK_TOKEN_SECRET=your_token_secret
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=bookstack_rag
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
OPENAI_API_KEY=sk-...

# Embedding provider: openai | local
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_FAIL_FAST_ON_QUOTA=true

# Optional tuning
SYNC_BATCH_SIZE=50
BOOKSTACK_REQUESTS_PER_SECOND=5
BOOKSTACK_MAX_RETRIES=4
EMBEDDING_MAX_RETRIES=4
RETRY_BACKOFF_SECONDS=1.0

# Optional Chroma connection (default: local persistent mode)
CHROMA_USE_HTTP=false
CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION_NAME=bookstack_documents
CHROMA_PATH=./chroma_data

# Docker compose host-side Postgres port mapping
POSTGRES_HOST_PORT=5433
```

Notes:

- `BOOKSTACK_URL` can be either `https://host` or `https://host/api`.
- If `CHROMA_USE_HTTP=false` (default), vectors are stored locally in `CHROMA_PATH` (default `./chroma_data`) and no Chroma server is required.
- If `CHROMA_USE_HTTP=true`, the pipeline connects to a running Chroma server.
- `EMBEDDING_PROVIDER=local` avoids OpenAI quota issues and is recommended for local development.
- `EMBEDDING_PROVIDER=openai` uses `text-embedding-3-large` and requires a valid billed key.

## Docker Compose (PostgreSQL + Chroma Persistence)

Start services:

```bash
docker compose up -d
```

Stop services:

```bash
docker compose down
```

Services use named volumes for persistence:

- `postgres_data`
- `chroma_data`

The compose file maps PostgreSQL container port `5432` to host port `${POSTGRES_HOST_PORT:-5433}` to avoid collisions with existing local PostgreSQL instances.

If you intentionally want Chroma over HTTP, set:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
CHROMA_USE_HTTP=true
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

## Database Migrations

This project uses Alembic migrations tracked in the `alembic_version` table.

Run migrations manually:

```bash
python3 scripts/db_migrate.py
```

Migration policy:

- **Manual by default**: schema updates should be applied with `python3 scripts/db_migrate.py`.
- **Auto bootstrap only once**: ingestion auto-runs migrations only when the DB is fresh and `alembic_version` does not exist yet.
- If `alembic_version` already exists, ingestion does not apply new migrations automatically.

## Implementation Deep Dives

- Low-level architecture and internals: [docs/LOW_LEVEL_IMPLEMENTATION.md](docs/LOW_LEVEL_IMPLEMENTATION.md)
- Low-level architecture diagrams: [docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md](docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md)
- Database module details: [app/db/README.md](app/db/README.md)
- Audit trail SQL examples: [docs/LOW_LEVEL_IMPLEMENTATION.md](docs/LOW_LEVEL_IMPLEMENTATION.md)

## Analysis Checklist

Use this quick checklist when validating a run:

1. Confirm migration head in `alembic_version`.
2. Inspect latest `ingestion_runs` row and verify `status`, `processed_pages`, and `failed_pages`.
3. Inspect `page_sync_audit` decision mix (`NEW/UPDATED/UNCHANGED/DELETED/SKIPPED_LOCKED/FAILED`).
4. Compare PostgreSQL `document_chunks` count against expected source content changes.
5. Verify Chroma collection `bookstack_documents` count for vector consistency.
6. For mismatches, inspect chunk delta flow in [docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md](docs/LOW_LEVEL_ARCHITECTURE_DIAGRAMS.md).

## PostgreSQL Schema

Tables are created by Alembic revision scripts.

Schema created:

### `documents`

- `page_id` (PK)
- `title`
- `book_slug`
- `chapter_id`
- `updated_at`
- `last_synced_at`

### `document_chunks`

- `chunk_id` (PK)
- `page_id` (FK -> documents.page_id)
- `chunk_index`
- `chunk_text`
- `vector_id`
- `created_at`

### `ingestion_runs`

- `run_id` (PK)
- `started_at`
- `finished_at`
- `status`
- `processed_pages`
- `failed_pages`
- `notes`

### `page_sync_audit`

- `audit_id` (PK)
- `run_id` (FK -> ingestion_runs.run_id)
- `page_id`
- `status`
- `reason`
- `source_updated_at`
- `local_updated_at`
- `created_at`

## How Ingestion Works

When you run ingestion:

1. Fetches pages from `GET /api/pages`
2. Checks each page against local metadata (`updated_at`)
3. Splits candidates into batches (`SYNC_BATCH_SIZE`)
4. Acquires per-page advisory lock for idempotency
5. Purges pages deleted upstream from both Chroma and PostgreSQL
6. Processes only new/updated pages not locked by another worker
7. Loads full page via `GET /api/pages/{id}`
8. Parses markdown to clean text
9. Analyzes section structure
10. Chunks text by tokens
11. Computes chunk-level delta against stored chunks
12. Re-embeds only changed/new chunks (with retry/backoff)
13. Deletes removed chunks from Chroma and PostgreSQL
14. Stores document + chunk metadata updates in PostgreSQL

## Run

From project root:

```bash
python3 scripts/run_ingestion.py
```

## Notes

- Chroma persists data in `./chroma_data` by default.
- Re-indexed pages are processed with chunk-level delta updates (changed/new/delete only).
- If your BookStack returns timestamps with `Z`, they are converted to UTC-aware datetimes.

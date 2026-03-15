# DB Module Notes

This folder contains relational persistence and migration integration.

## Files

- `base.py`: SQLAlchemy declarative base.
- `models.py`: ORM entities for `documents` and `document_chunks`.
- `session.py`: SQLAlchemy engine and unit-of-work style session scope.
- `metadata_store.py`: repository methods used by the ingestion pipeline.
- `migration_runner.py`: Alembic programmatic upgrade executor.
- `vector_store.py`: Chroma persistence adapter (vector DB).

## Why ORM Here

- Strong typing and maintainable data access code.
- Easier unit testing with session-level mocking/fakes.
- Cleaner transition to richer relational features (constraints, joins, computed fields).
- Better alignment with Alembic and schema evolution workflows.

## Locking

`metadata_store.acquire_page_lock()` uses PostgreSQL advisory locks so concurrent workers cannot process the same page simultaneously.

## Delta Logic Data Contract

`get_document_chunks(page_id)` returns map keyed by `vector_id` so pipeline can efficiently compute:

- deleted ids (existing - desired)
- changed/new ids (text mismatch or absent)

This enables chunk-level differential updates instead of full-page reindex every run.

# Low-Level Architecture Diagrams

This document provides analysis-focused architecture diagrams for the BookStack ingestion pipeline.

## 1) System Context

```mermaid
flowchart LR
    BS[BookStack API]
    ING[Ingestion Pipeline]
    PG[(PostgreSQL)]
    CH[(Chroma)]

    BS -->|pages + page details| ING
    ING -->|document + chunk metadata| PG
    ING -->|embeddings + chunk docs| CH
```

## 2) Runtime Component Flow

```mermaid
flowchart TD
    A[run_ingestion.py] --> B[Settings]
    B --> C[IngestionPipeline.run]
    C --> D[MigrationRunner]
    C --> E[BookStackClient]
    C --> F[DocumentSyncService]
    C --> G[MetadataStore]
    C --> H[VectorStore]

    E --> I[DocumentLoader]
    I --> J[ContentParser]
    J --> K[StructureAnalyzer]
    K --> L[ChunkingEngine]
    L --> M[MetadataEnricher]
    M --> N[EmbeddingService]

    N --> H
    M --> G
```

## 3) Ingestion Sequence (Per Run)

```mermaid
sequenceDiagram
    participant Runner as run_ingestion.py
    participant Pipe as IngestionPipeline
    participant Mig as MigrationRunner
    participant API as BookStackClient
    participant Meta as MetadataStore
    participant Vec as VectorStore
    participant Emb as EmbeddingService

    Runner->>Pipe: run()
    Pipe->>Mig: upgrade to head
    Pipe->>Meta: start_ingestion_run()
    Pipe->>API: get_pages()
    Pipe->>Meta: list_document_page_ids()
    Pipe->>Pipe: compute deleted_page_ids

    loop per deleted page
        Pipe->>Meta: acquire_page_lock(page_id)
        Pipe->>Vec: delete_page_chunks(page_id)
        Pipe->>Meta: delete_document(page_id)
        Pipe->>Meta: record_page_audit(DELETED)
    end

    Pipe->>Pipe: classify_pages()

    loop per candidate page
        Pipe->>Meta: acquire_page_lock(page_id)
        alt lock acquired
            Pipe->>API: get_page(page_id)
            Pipe->>Pipe: parse -> analyze -> chunk
            Pipe->>Meta: get_document_chunks(page_id)
            Pipe->>Pipe: compute chunk delta
            Pipe->>Vec: delete removed chunk ids
            Pipe->>Meta: delete removed chunk rows
            Pipe->>Emb: embed changed/new chunk texts
            Pipe->>Vec: upsert changed/new chunks
            Pipe->>Meta: upsert_document()
            Pipe->>Meta: upsert_document_chunks()
            Pipe->>Meta: record_page_audit(NEW/UPDATED)
        else lock busy
            Pipe->>Meta: record_page_audit(SKIPPED_LOCKED)
        end
    end

    Pipe->>Meta: finish_ingestion_run(SUCCESS/PARTIAL_SUCCESS/FAILED)
```

## 4) Relational Data Model

```mermaid
erDiagram
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : has
    INGESTION_RUNS ||--o{ PAGE_SYNC_AUDIT : records

    DOCUMENTS {
      bigint page_id PK
      text title
      text book_slug
      bigint chapter_id
      timestamptz updated_at
      timestamptz last_synced_at
    }

    DOCUMENT_CHUNKS {
      bigint chunk_id PK
      bigint page_id FK
      int chunk_index
      text chunk_text
      text vector_id UNIQUE
      timestamptz created_at
    }

    INGESTION_RUNS {
      bigint run_id PK
      timestamptz started_at
      timestamptz finished_at
      text status
      int processed_pages
      int failed_pages
      text notes
    }

    PAGE_SYNC_AUDIT {
      bigint audit_id PK
      bigint run_id FK
      bigint page_id
      text status
      text reason
      timestamptz source_updated_at
      timestamptz local_updated_at
      timestamptz created_at
    }
```

## 5) Page Decision State Model

```mermaid
stateDiagram-v2
    [*] --> Candidate
    Candidate --> NEW: no local document
    Candidate --> UPDATED: remote updated_at > local
    Candidate --> UNCHANGED: remote updated_at <= local

    NEW --> PROCESSED
    UPDATED --> PROCESSED
    UNCHANGED --> [*]

    PROCESSED --> FAILED: exception during processing
    PROCESSED --> SKIPPED_LOCKED: lock unavailable
    PROCESSED --> [*]: success

    [*] --> DELETED: present locally, absent remotely
```

## 6) Chunk Delta Decision Logic

```mermaid
flowchart TD
    A[Build desired chunks from current page] --> B[Load existing chunks by vector_id]
    B --> C{Existing - Desired}
    C -->|non-empty| D[Delete removed chunk ids in Chroma + Postgres]
    C -->|empty| E[No deletions]

    B --> F{Desired chunk missing or text changed?}
    F -->|yes| G[Embed + upsert changed/new chunks]
    F -->|no| H[Skip embedding for unchanged chunks]

    D --> I[Upsert documents row]
    E --> I
    G --> I
    H --> I
```

## 7) Failure and Recovery Paths

```mermaid
flowchart LR
    A[API/network error] --> B[BookStack retry/backoff]
    C[Embedding provider error] --> D[Embedding retry/backoff]
    E[Quota exhausted] --> F[Fail fast in run if configured]
    G[Concurrent worker same page] --> H[Advisory lock -> SKIPPED_LOCKED]
    I[Pipeline-level exception] --> J[Run status FAILED]

    B --> K[Next page or retry success]
    D --> K
    F --> J
    H --> K
```

## 8) How To Use These Diagrams

- Start with System Context to orient storage boundaries.
- Use the Ingestion Sequence diagram to debug a single run.
- Use the Chunk Delta diagram when vector counts do not match expected text changes.
- Use the State Model with `page_sync_audit` to explain why a page was or was not reprocessed.

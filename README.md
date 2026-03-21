# BookStack RAG Ingestion

A production-grade RAG (Retrieval-Augmented Generation) system that syncs content from a [BookStack](https://www.bookstackapp.com/) instance, chunks and embeds documents, and exposes a full API for semantic search, LLM-powered answers, and multi-turn chat.

## Features

- **Document ingestion** — Syncs pages from BookStack, parses Markdown/HTML, splits into token-aware chunks, generates embeddings, and stores in ChromaDB + PostgreSQL
- **Semantic search** — Vector similarity search with optional keyword boosting, metadata filtering, and cross-encoder reranking
- **LLM answers** — Generate natural-language answers from retrieved context using OpenAI models
- **Multi-turn chat** — Conversational RAG with session history, archiving, and WebSocket streaming
- **Incremental sync** — Only re-processes pages that changed since the last run, with full audit trail
- **Parallel processing** — Concurrent page processing with advisory locks for thread safety
- **Structured logging** — JSON-formatted logs via structlog for production observability

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- A BookStack instance with API tokens
- OpenAI API key (or use local embeddings)

### 1. Clone and install

```bash
git clone <repository-url>
cd bookstack-rag-ingestion

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your settings — at minimum:

```env
BOOKSTACK_URL=https://bookstack.example.com
BOOKSTACK_TOKEN_ID=your_token_id
BOOKSTACK_TOKEN_SECRET=your_token_secret

# Use local embeddings (no API key needed)
EMBEDDING_PROVIDER=local

# Or use OpenAI
# EMBEDDING_PROVIDER=openai
# OPENAI_API_KEY=sk-your-key
```

### 3. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (port 5433) and ChromaDB (port 8000).

### 4. Run database migrations

```bash
python scripts/db_migrate.py upgrade
```

### 5. Run ingestion

```bash
python scripts/run_ingestion.py
```

### 6. Start the API

```bash
python scripts/run_query_api.py
```

The API is available at `http://localhost:8001`. All routes are served under `/api/v1/`.
Interactive docs: `http://localhost:8001/docs`.

## Project Structure

```
├── app/
│   ├── api/                  # FastAPI application, routes, schemas, middleware
│   │   ├── routes/v1/        # Versioned endpoint handlers (query, chat, ingestion, metrics)
│   │   ├── middleware/       # Error handler and request-context middleware
│   │   ├── schemas/v1.py     # Centralized Pydantic request/response models
│   │   ├── pagination.py     # Shared pagination helpers
│   │   └── main.py           # App factory, middleware registration
│   ├── config/               # Pydantic Settings, constants, logging
│   ├── domain/               # Business entities and repository interfaces
│   ├── infrastructure/       # Concrete implementations (DB, vectors, embeddings)
│   ├── services/             # Business logic orchestration
│   ├── pipelines/            # Ingestion pipeline
│   ├── chunking/             # Token-aware text splitting
│   ├── embeddings/           # Embedding generation (OpenAI / local)
│   ├── parsers/              # Markdown and HTML parsing
│   ├── analyzers/            # Document structure analysis
│   ├── metadata/             # Chunk metadata enrichment
│   ├── sync/                 # Incremental sync logic
│   ├── chat/                 # Chat service
│   ├── llm/                  # LLM answer generation
│   ├── retrieval/            # Vector retrieval and reranking
│   └── utils/                # Token counting, embedding cache
├── db/alembic/               # Database migration scripts
├── scripts/                  # CLI entry points
├── docker-compose.yml        # PostgreSQL + ChromaDB
└── .env.example              # Configuration template
```

## Configuration

All configuration is managed through environment variables (or a `.env` file) using Pydantic Settings with validation. See [.env.example](.env.example) for the full list with defaults.

Key configuration groups:

| Group | Variables | Purpose |
|-------|-----------|---------|
| Database | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL connection |
| BookStack | `BOOKSTACK_URL`, `BOOKSTACK_TOKEN_ID`, `BOOKSTACK_TOKEN_SECRET` | API access |
| Embeddings | `EMBEDDING_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL` | Embedding generation |
| Vector Store | `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION_NAME` | ChromaDB connection |
| Ingestion | `CHUNK_SIZE`, `CHUNK_OVERLAP`, `SYNC_BATCH_SIZE`, `MAX_WORKERS` | Pipeline tuning |
| LLM | `LLM_MODEL`, `ENABLE_LLM_GENERATION`, `ENABLE_RERANKING` | Answer generation |
| Chat | `ENABLE_CHAT`, `CHAT_HISTORY_LIMIT` | Chat system |
| API | `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `RATE_LIMIT_PER_MINUTE` | Server settings |
| Observability | `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL`, `LOG_JSON` | Runtime environment and logging |

## Database Schema

| Table | Purpose |
|-------|---------|
| `documents` | Tracked BookStack pages with sync timestamps |
| `document_chunks` | Text chunks linked to documents and vector IDs |
| `ingestion_runs` | Ingestion run history and status |
| `page_sync_audit` | Per-page sync audit trail |
| `chat_sessions` | Chat session metadata |
| `chat_messages` | Conversation messages with token tracking |
| `query_cache` | Cached query results with TTL |

Migrations are managed with Alembic — see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for details.

## Documentation

- [API_DOCS.md](API_DOCS.md) — Complete API reference with request/response examples for all 20 endpoints
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design, data flow, and layer descriptions
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — Development workflow and extension guide

## License

MIT

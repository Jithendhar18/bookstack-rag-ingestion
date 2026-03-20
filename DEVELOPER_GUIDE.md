# Developer Guide

## Development Setup

```bash
# Clone and create virtual environment
git clone <repository-url>
cd bookstack-rag-ingestion
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env

# Start infrastructure
docker compose up -d

# Run migrations
python scripts/db_migrate.py upgrade
```

For development, set in `.env`:

```env
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
LOG_JSON=false
EMBEDDING_PROVIDER=local
ENABLE_PARALLEL_PROCESSING=false
```

## Configuration System

Configuration is managed via Pydantic Settings in `app/config/settings.py`. All values come from environment variables or `.env` files.

Settings are grouped into logical sections:

```python
from app.config.settings import get_settings

settings = get_settings()

# Grouped access
settings.database.sqlalchemy_url
settings.bookstack.api_base
settings.embeddings.provider
settings.ingestion.chunk_size
settings.api.port

# Flat access (backward-compatible)
settings.postgres_host
settings.embedding_provider
settings.api_port
```

Groups: `database`, `bookstack`, `embeddings`, `vector_store`, `cache`, `ingestion`, `llm`, `chat`, `api`.

Cross-field validation is built in — for example, `OPENAI_API_KEY` is required when `EMBEDDING_PROVIDER=openai`, and `CHUNK_OVERLAP` must be less than `CHUNK_SIZE`.

See [.env.example](.env.example) for all available variables with defaults.

## Adding a New API Endpoint

Follow the clean architecture pattern — domain first, then infrastructure, service, and API.

### 1. Define domain entity (if needed)

```python
# app/domain/entities/__init__.py
@dataclass
class Widget:
    id: int
    name: str
    created_at: datetime
```

### 2. Define repository interface

```python
# app/domain/repositories/__init__.py
class IWidgetRepository(ABC):
    @abstractmethod
    def get_by_id(self, widget_id: int) -> Widget | None: ...

    @abstractmethod
    def save(self, widget: Widget) -> Widget: ...
```

### 3. Implement repository

```python
# app/infrastructure/database/repositories/__init__.py
class WidgetRepository(IWidgetRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, widget_id: int) -> Widget | None:
        orm = self.session.query(WidgetORM).filter_by(id=widget_id).first()
        return self._to_domain(orm) if orm else None
```

### 4. Create service

```python
# app/services/widget_service.py
class WidgetService:
    def __init__(self, repo: IWidgetRepository):
        self.repo = repo

    def get_widget(self, widget_id: int) -> Widget:
        widget = self.repo.get_by_id(widget_id)
        if not widget:
            raise WidgetNotFound(widget_id)
        return widget
```

### 5. Add dependency injection

```python
# app/api/dependencies.py
def get_widget_service(db: Session = Depends(get_db)) -> WidgetService:
    return WidgetService(repo=WidgetRepository(db))
```

### 6. Create route

```python
# app/api/routes/widgets.py
router = APIRouter(prefix="/widgets", tags=["widgets"])

@router.get("/{widget_id}")
async def get_widget(
    widget_id: int,
    service: WidgetService = Depends(get_widget_service),
):
    widget = service.get_widget(widget_id)
    return WidgetResponse.from_domain(widget)
```

### 7. Register the router

```python
# app/api/main.py
from app.api.routes.widgets import router as widgets_router
app.include_router(widgets_router)
```

## Database Migrations

Migrations use Alembic. Scripts live in `db/alembic/versions/`.

```bash
# Apply all pending migrations
python scripts/db_migrate.py upgrade

# Rollback one migration
python scripts/db_migrate.py downgrade

# Create a new migration
cd db && alembic revision -m "add_widgets_table"
```

Migration files follow the naming convention `YYYYMMDD_NNNN_description.py`.

## Logging

The project uses structlog for structured logging. Configuration is in `app/config/logging.py`.

```python
import structlog

logger = structlog.get_logger(__name__)

# Basic logging
logger.info("processing_page", page_id=42, title="Setup Guide")
logger.error("sync_failed", page_id=42, error=str(e))

# With bound context
log = logger.bind(run_id=5, batch=1)
log.info("batch_started", page_count=50)
```

Set `LOG_JSON=true` in production for machine-readable logs. Set `LOG_JSON=false` in development for colored console output.

## Embedding Providers

The system supports two embedding providers, configured via `EMBEDDING_PROVIDER`:

**OpenAI** (`openai`) — Production-grade. Requires `OPENAI_API_KEY`. Default model: `text-embedding-3-large`.

**Local** (`local`) — No API key needed. Uses sentence-transformers. Default model: `sentence-transformers/all-MiniLM-L6-v2`. Runs on CPU.

The embedding cache (`ENABLE_EMBEDDING_CACHE=true`) avoids redundant API calls. Supports in-memory or Redis backends.

## Ingestion Pipeline Tuning

Key parameters for the ingestion pipeline:

| Variable | Default | Effect |
|----------|---------|--------|
| `CHUNK_SIZE` | 500 | Tokens per chunk (higher = more context, fewer chunks) |
| `CHUNK_OVERLAP` | 100 | Overlapping tokens between chunks (helps continuity) |
| `SYNC_BATCH_SIZE` | 50 | Pages processed per batch |
| `ENABLE_PARALLEL_PROCESSING` | true | Concurrent page processing |
| `MAX_WORKERS` | 4 | Thread count for parallel processing |

For large instances (100K+ pages):

```env
SYNC_BATCH_SIZE=100
MAX_WORKERS=8
EMBEDDING_CACHE_TYPE=redis
```

For debugging:

```env
ENABLE_PARALLEL_PROCESSING=false
SYNC_BATCH_SIZE=5
LOG_LEVEL=DEBUG
```

## Running the API

Three entry points are available:

```bash
# Full API — all features (query, chat, ingestion, health)
python scripts/run_complete_api.py

# Query-only API
python scripts/run_query_api.py

# Ingestion CLI (no API server)
python scripts/run_ingestion.py
```

The API server runs on `http://localhost:8001` by default (configurable via `API_PORT`).

## Project Conventions

- **Architecture**: Clean architecture — domain has no framework imports, services use repository interfaces, routes are thin HTTP handlers
- **Configuration**: All settings via environment variables, validated by Pydantic
- **Logging**: structlog with bound context — always include relevant IDs (page_id, run_id, session_id)
- **Formatting**: black (line-length=100), isort (profile=black)
- **Type hints**: All function signatures are type-annotated
- **Migrations**: Alembic with descriptive revision names

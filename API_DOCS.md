# API Reference

Base URL: `http://localhost:8001`
API prefix: `/api/v1`

Interactive docs: `http://localhost:8001/docs` | ReDoc: `http://localhost:8001/redoc`

---

## Conventions

### Pagination

List endpoints accept `?page=1&limit=20` query parameters and return a standard envelope:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "limit": 20
}
```

### Error Format

All errors (validation, domain, and unexpected) return a consistent structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": {}
  }
}
```

| Code | HTTP status | When |
|------|-------------|------|
| `VALIDATION_ERROR` | 422 | Request body fails schema validation |
| `NOT_FOUND` | 404 | Session, run, or page not found |
| `SERVICE_UNAVAILABLE` | 503 | Database or vector store unreachable |
| `INTERNAL_ERROR` | 500 | Unexpected server-side error |

### Request IDs

Every response includes an `x-request-id` header (UUID) for distributed tracing. Pass `x-request-id` in the request to propagate your own ID.

---

## Query

### POST /api/v1/query

Semantic search with optional reranking and LLM answer generation.

**Request:**

```json
{
  "query": "How do I configure OAuth2?",
  "top_k": 5,
  "filters": {
    "page_id": 42,
    "page_title": "Security",
    "section_path": "Authentication",
    "document_title": "Admin Guide"
  },
  "use_llm": false,
  "rerank": false,
  "include_sources": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query text |
| `top_k` | integer | 5 | Number of results to return |
| `filters` | object | null | Metadata filters (all optional) |
| `use_llm` | boolean | false | Generate an LLM answer from retrieved context |
| `rerank` | boolean | false | Apply cross-encoder reranking |
| `include_sources` | boolean | true | Include chunk metadata in results |

**Response:**

```json
{
  "answer": "OAuth2 is configured by setting...",
  "results": [
    {
      "chunk_id": "chunk_001",
      "chunk_text": "OAuth2 is configured by setting...",
      "score": 0.89,
      "metadata": {
        "page_id": 42,
        "page_title": "Security Setup",
        "section_path": "Authentication > OAuth2",
        "chunk_index": 0
      }
    }
  ],
  "sources": ["Security Setup", "Admin Guide"],
  "latency_ms": 52
}
```

**Example:**

```bash
curl -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is IVA Digital in Chile?", "top_k": 5, "use_llm": true}'
```

---

## Chat

### POST /api/v1/chat/session

Create a new chat session.

**Request:**

```json
{
  "user_id": "user123",
  "title": "Technical Questions"
}
```

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user123",
  "title": "Technical Questions",
  "created_at": "2026-03-20T10:30:00Z",
  "is_archived": false
}
```

---

### GET /api/v1/chat/sessions

List all chat sessions with pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `limit` | integer | 20 | Results per page (max 100) |

**Response:** Standard paginated envelope with `ChatSessionResponse` items.

---

### GET /api/v1/chat/session/{session_id}

Retrieve full conversation history for a session.

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user123",
  "created_at": "2026-03-20T10:30:00Z",
  "messages": [
    {
      "role": "user",
      "content": "How do I configure OAuth2?",
      "created_at": "2026-03-20T10:31:00Z"
    },
    {
      "role": "assistant",
      "content": "OAuth2 is configured by...",
      "created_at": "2026-03-20T10:31:15Z"
    }
  ]
}
```

---

### DELETE /api/v1/chat/session/{session_id}

Permanently delete a session and all its messages.

---

### POST /api/v1/chat/session/{session_id}/archive

Soft-delete (archive) a session without losing history.

---

### POST /api/v1/chat/message

Send a message and receive a full RAG-powered response.

**Request:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "How do I configure OAuth2?",
  "top_k": 5,
  "use_reranking": true
}
```

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "assistant_response": "OAuth2 is configured by...",
  "sources": [
    {
      "page_id": 42,
      "page_title": "Security Setup",
      "score": 0.87
    }
  ],
  "tokens_used": 250
}
```

---

### POST /api/v1/chat/message/stream

Send a message and receive the response as a **Server-Sent Events (SSE)** stream.
Tokens are delivered incrementally as they are generated.

**Request:** Same body as `POST /api/v1/chat/message`.

**Response:** `text/event-stream` content type. Each event is a JSON object on a `data:` line.

```
data: {"token": "OAuth2"}

data: {"token": " is configured"}

data: {"token": " by..."}

data: {"done": true, "sources": [{"page_id": 42, "page_title": "Security Setup", "score": 0.87}]}
```

**Example (curl):**

```bash
curl -N -X POST http://localhost:8001/api/v1/chat/message/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "550e8400-...", "message": "Explain the auth flow"}'
```

**Example (JavaScript fetch):**

```js
const resp = await fetch("http://localhost:8001/api/v1/chat/message/stream", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({session_id: "550e8400-...", message: "Explain the auth flow"})
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  const lines = decoder.decode(value).split("\n");
  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const event = JSON.parse(line.slice(6));
      if (event.done) { console.log("Sources:", event.sources); break; }
      process.stdout.write(event.token);
    }
  }
}
```

---

### WS /api/v1/chat/ws/{session_id}

WebSocket endpoint for real-time bidirectional streaming chat.

**Connect:**

```bash
wscat -c "ws://localhost:8001/api/v1/chat/ws/550e8400-..."
```

**Send:**

```json
{"message": "Explain the authentication flow", "top_k": 5, "use_reranking": true}
```

**Receive:**

```json
{"type": "response", "response": "The authentication flow...", "sources": []}
```

---

## Ingestion

### POST /api/v1/ingestion/run

Start an asynchronous document sync from BookStack. Always runs in the background —
poll the status endpoint to track progress.

**Request:**

```json
{
  "full_sync": false,
  "page_ids": [42, 101, 203],
  "force": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `full_sync` | boolean | false | Clear existing indexes and re-sync everything |
| `page_ids` | array[int] | null | Sync only these specific page IDs (partial sync) |
| `force` | boolean | false | Re-process pages even if unchanged |

**Response (202 Accepted):**

```json
{
  "run_id": 25,
  "status": "STARTED",
  "started_at": "2026-03-20T10:30:00Z"
}
```

---

### GET /api/v1/ingestion/run/{run_id}/status

Lightweight poll endpoint for tracking an async ingestion run.

**Response:**

```json
{
  "run_id": 25,
  "status": "RUNNING",
  "processed_pages": 87,
  "failed_pages": 1
}
```

Status values: `STARTED` -> `RUNNING` -> `COMPLETED` | `FAILED`

---

### GET /api/v1/ingestion/runs

List all ingestion runs with pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `limit` | integer | 20 | Results per page |

**Response:** Standard paginated envelope with `IngestionRunResponse` items.

---

### GET /api/v1/ingestion/runs/{run_id}

Full details for a single ingestion run.

**Response:**

```json
{
  "run_id": 25,
  "status": "COMPLETED",
  "started_at": "2026-03-20T10:30:00Z",
  "finished_at": "2026-03-20T11:15:00Z",
  "processed_pages": 150,
  "failed_pages": 2,
  "notes": "Incremental sync - 150 pages updated"
}
```

---

### GET /api/v1/ingestion/audit/page/{page_id}

Page-level sync audit history.

**Response:**

```json
[
  {
    "audit_id": 1,
    "page_id": 42,
    "status": "SYNCED",
    "reason": "Page updated in source",
    "source_updated_at": "2026-03-20T09:00:00Z",
    "created_at": "2026-03-20T10:05:30Z"
  }
]
```

---

### GET /api/v1/ingestion/audit/run/{run_id}

All audit records for a given ingestion run.

---

### GET /api/v1/ingestion/stats

Overall ingestion statistics.

**Response:**

```json
{
  "total_runs": 25,
  "completed_runs": 23,
  "failed_runs": 1,
  "running_runs": 1,
  "latest_run_id": 25,
  "latest_run_status": "STARTED",
  "latest_run_at": "2026-03-20T11:00:00Z"
}
```

---

## Metrics

### GET /api/v1/metrics

All system performance metrics collected since startup.

**Response:**

```json
{
  "metrics": {
    "query_count": 142,
    "avg_query_latency_ms": 87,
    "cache_hit_rate": 0.34,
    "ingestion_run_count": 5
  },
  "collected_at": "2026-03-20T11:30:00Z"
}
```

---

### GET /api/v1/metrics/queries

Query-specific performance metrics.

---

### GET /api/v1/metrics/ingestion

Ingestion metrics - database counts and pipeline performance.

---

## Health

### GET /health/

Comprehensive health check for all backend services.

**Response (200 OK):**

```json
{
  "status": "healthy",
  "timestamp": "2026-03-20T10:30:45Z",
  "services": {
    "database": "healthy",
    "vector_store": "healthy",
    "embedding_service": "healthy"
  }
}
```

Returns HTTP 503 if any service is unhealthy.

---

### GET /health/ready

Kubernetes-compatible readiness probe.

**Response (200 OK):**

```json
{"ready": true}
```

Returns HTTP 503 with `{"ready": false, "reason": "..."}` if not ready.

---

## Usage Examples

### Async Ingestion Flow

```bash
# Start a partial sync for specific pages
curl -X POST http://localhost:8001/api/v1/ingestion/run \
  -H "Content-Type: application/json" \
  -d '{"page_ids": [42, 101], "force": true}'

# Poll for completion
curl http://localhost:8001/api/v1/ingestion/run/26/status

# View full run details
curl http://localhost:8001/api/v1/ingestion/runs/26
```

### Chat with SSE Streaming (Python)

```python
import requests, json

BASE = "http://localhost:8001/api/v1"

# Create session
session = requests.post(f"{BASE}/chat/session", json={
    "user_id": "alice", "title": "Setup Help"
}).json()
session_id = session["session_id"]

# Stream a reply
with requests.post(
    f"{BASE}/chat/message/stream",
    json={"session_id": session_id, "message": "How do I set up the database?"},
    stream=True
) as resp:
    for raw_line in resp.iter_lines():
        if raw_line and raw_line.startswith(b"data: "):
            event = json.loads(raw_line[6:])
            if event.get("done"):
                print("\nSources:", event.get("sources"))
                break
            print(event["token"], end="", flush=True)
```

### Query with LLM (curl)

```bash
curl -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the recommended production configuration?",
    "top_k": 5,
    "use_llm": true,
    "rerank": true
  }'
```

### Full Sync and Monitor (curl)

```bash
# Trigger full re-sync
curl -X POST http://localhost:8001/api/v1/ingestion/run \
  -H "Content-Type: application/json" \
  -d '{"full_sync": true}'

# Check overall stats
curl http://localhost:8001/api/v1/ingestion/stats

# View performance metrics
curl http://localhost:8001/api/v1/metrics
```

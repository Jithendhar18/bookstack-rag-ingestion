# API Reference

Base URL: `http://localhost:8001`

Interactive docs: `http://localhost:8001/docs` | ReDoc: `http://localhost:8001/redoc`

---

## Query

### POST /query/

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
    "document_title": "Admin Guide",
    "chunk_index": 0
  },
  "use_llm": false,
  "use_reranking": false,
  "include_metadata": true,
  "keyword_boost": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query text |
| `top_k` | integer | 5 | Number of results to return |
| `filters` | object | null | Metadata filters (all optional) |
| `use_llm` | boolean | false | Generate an LLM answer from retrieved context |
| `use_reranking` | boolean | false | Apply cross-encoder reranking |
| `include_metadata` | boolean | true | Include chunk metadata in results |
| `keyword_boost` | boolean | false | Boost results matching query keywords |

**Response:**

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "How do I configure OAuth2?",
  "num_results": 3,
  "results": [
    {
      "chunk_id": "chunk_001",
      "chunk_text": "OAuth2 is configured by setting...",
      "score": 0.89,
      "metadata": {
        "page_id": 42,
        "page_title": "Security Setup",
        "section_path": "Authentication > OAuth2",
        "section_level": 2,
        "chunk_index": 0,
        "document_title": "Admin Guide"
      }
    }
  ],
  "answer": null,
  "metrics": {
    "retrieval_time_ms": 45,
    "llm_time_ms": 0,
    "total_time_ms": 52,
    "cache_hit": false
  }
}
```

**Example:**

```bash
curl -X POST http://localhost:8001/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is IVA Digital in Chile?", "top_k": 5, "use_llm": true}'
```

---

### POST /query/batch

Execute multiple queries in a single request.

**Request:**

```json
{
  "queries": [
    {"query": "Authentication methods", "top_k": 3},
    {"query": "Database setup", "use_llm": true}
  ]
}
```

**Response:**

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_queries": 2,
  "results": [
    {
      "query_index": 0,
      "request_id": "...",
      "query": "Authentication methods",
      "num_results": 3,
      "results": [],
      "answer": null,
      "metrics": {}
    }
  ],
  "errors": []
}
```

---

## Chat

### POST /chat/session

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
  "updated_at": "2026-03-20T10:30:00Z",
  "is_archived": false
}
```

---

### POST /chat/message

Send a message and get a RAG-powered response.

**Request:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "How do I configure OAuth2?",
  "top_k": 5,
  "filters": null,
  "use_reranking": true,
  "user_id": "user123"
}
```

**Response:**

```json
{
  "request_id": "...",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message_count": 3,
  "assistant_response": "OAuth2 is configured by...",
  "sources": [
    {
      "chunk_id": "chunk_001",
      "page_id": 42,
      "page_title": "Security Setup",
      "score": 0.87
    }
  ],
  "tokens_used": 250
}
```

---

### GET /chat/session/{session_id}

Retrieve full conversation history.

**Response:**

```json
{
  "session_id": "...",
  "user_id": "user123",
  "created_at": "2026-03-20T10:30:00Z",
  "updated_at": "2026-03-20T10:45:00Z",
  "message_count": 4,
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "content": "How do I configure OAuth2?",
      "tokens_used": null,
      "created_at": "2026-03-20T10:31:00Z"
    },
    {
      "message_id": "msg_002",
      "role": "assistant",
      "content": "OAuth2 is configured by...",
      "tokens_used": 250,
      "created_at": "2026-03-20T10:31:15Z"
    }
  ]
}
```

---

### GET /chat/sessions

List chat sessions with pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | string | null | Filter by user |
| `limit` | integer | 50 | Max results (up to 500) |
| `offset` | integer | 0 | Pagination offset |

**Response:**

```json
{
  "sessions": [
    {
      "session_id": "...",
      "user_id": "user123",
      "title": "Technical Questions",
      "created_at": "2026-03-20T10:30:00Z",
      "is_archived": false
    }
  ],
  "total": 5,
  "limit": 50,
  "offset": 0
}
```

---

### DELETE /chat/session/{session_id}

Permanently delete a session and all its messages.

**Response:**

```json
{"message": "Session 550e8400-... deleted"}
```

---

### POST /chat/session/{session_id}/archive

Soft-delete (archive) a session.

**Response:**

```json
{"message": "Session 550e8400-... archived"}
```

---

### WS /chat/ws/{session_id}

WebSocket endpoint for real-time streaming chat.

**Connect:**

```bash
wscat -c "ws://localhost:8001/chat/ws/550e8400-..."
```

**Send:**

```json
{"message": "Explain the authentication flow", "top_k": 5, "use_reranking": true}
```

**Receive:**

```json
{"type": "response", "message_count": 2, "response": "The authentication flow...", "sources": []}
```

---

## Ingestion

### POST /ingestion/run

Start a document sync from BookStack.

**Request:**

```json
{
  "full_sync": false,
  "run_async": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `full_sync` | boolean | false | Clear existing indexes and re-sync everything |
| `run_async` | boolean | true | Run in background (non-blocking) |

**Response:**

```json
{
  "run_id": 1,
  "status": "STARTED",
  "started_at": "2026-03-20T10:30:00Z",
  "finished_at": null,
  "processed_pages": 0,
  "failed_pages": 0,
  "notes": "Full sync started..."
}
```

---

### GET /ingestion/runs

List ingestion runs with pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Max results (up to 500) |
| `offset` | integer | 0 | Pagination offset |
| `status` | string | null | Filter: `STARTED`, `COMPLETED`, `FAILED` |

**Response:**

```json
[
  {
    "run_id": 1,
    "status": "COMPLETED",
    "started_at": "2026-03-20T10:00:00Z",
    "finished_at": "2026-03-20T10:45:00Z",
    "processed_pages": 150,
    "failed_pages": 2
  }
]
```

---

### GET /ingestion/runs/{run_id}

Get details of a specific ingestion run.

---

### GET /ingestion/audit/page/{page_id}

Get sync history for a specific BookStack page.

**Response:**

```json
[
  {
    "audit_id": 1,
    "page_id": 42,
    "status": "SYNCED",
    "reason": "Page updated in source",
    "source_updated_at": "2026-03-20T09:00:00Z",
    "local_updated_at": "2026-03-20T10:05:00Z",
    "created_at": "2026-03-20T10:05:30Z"
  }
]
```

---

### GET /ingestion/audit/run/{run_id}

Get all audit records for an ingestion run.

---

### GET /ingestion/stats

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

## Health

### GET /health/

Comprehensive health check for all backend services.

**Response (200):**

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

**Response (200):**

```json
{"ready": true}
```

Returns HTTP 503 with `{"ready": false, "reason": "..."}` if not ready.

---

## Error Responses

All errors use a consistent format:

```json
{
  "detail": "Detailed error message",
  "request_id": "550e8400-...",
  "status_code": 400
}
```

| Code | Meaning |
|------|---------|
| 400 | Validation error (bad request body) |
| 404 | Resource not found (session, run) |
| 503 | Service unavailable (database, vector store down) |
| 500 | Internal server error |

---

## Usage Examples

### End-to-End Chat Flow (Python)

```python
import requests

BASE = "http://localhost:8001"

# Create session
session = requests.post(f"{BASE}/chat/session", json={
    "user_id": "alice", "title": "Setup Help"
}).json()

# Send message
reply = requests.post(f"{BASE}/chat/message", json={
    "session_id": session["session_id"],
    "message": "How do I set up the database?",
    "user_id": "alice"
}).json()
print(reply["assistant_response"])

# Follow-up (system retains history)
reply2 = requests.post(f"{BASE}/chat/message", json={
    "session_id": session["session_id"],
    "message": "What about backups?",
    "user_id": "alice"
}).json()
print(reply2["assistant_response"])
```

### Query with LLM (curl)

```bash
curl -X POST http://localhost:8001/query/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the recommended production configuration?",
    "top_k": 5,
    "use_llm": true,
    "use_reranking": true
  }'
```

### Monitor Ingestion (curl)

```bash
# Start sync
curl -X POST http://localhost:8001/ingestion/run \
  -H "Content-Type: application/json" \
  -d '{"full_sync": true, "run_async": true}'

# Check status
curl http://localhost:8001/ingestion/runs/1

# View stats
curl http://localhost:8001/ingestion/stats
```

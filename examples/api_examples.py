"""Complete end-to-end examples for the BookStack RAG API."""

import asyncio
import json
import requests
from typing import Optional


class BookStackRAGClient:
    """Python client for BookStack RAG API."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        """Initialize client.

        Args:
            base_url: API base URL
        """
        self.base_url = base_url.rstrip("/")

    # ============================================================================
    # INGESTION MANAGEMENT
    # ============================================================================

    def ingestion_start_full_sync(self) -> dict:
        """Start a full ingestion sync.

        Returns:
            Ingestion run response
        """
        response = requests.post(
            f"{self.base_url}/ingestion/run",
            json={"full_sync": True, "run_async": True},
        )
        response.raise_for_status()
        return response.json()

    def ingestion_start_incremental(self) -> dict:
        """Start an incremental ingestion sync.

        Returns:
            Ingestion run response
        """
        response = requests.post(
            f"{self.base_url}/ingestion/run",
            json={"full_sync": False, "run_async": True},
        )
        response.raise_for_status()
        return response.json()

    def ingestion_get_status(self, run_id: int) -> dict:
        """Get status of an ingestion run.

        Args:
            run_id: Ingestion run ID

        Returns:
            Ingestion run details
        """
        response = requests.get(f"{self.base_url}/ingestion/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def ingestion_list_runs(self, status: Optional[str] = None) -> list[dict]:
        """List ingestion runs.

        Args:
            status: Optional status filter (STARTED, COMPLETED, FAILED)

        Returns:
            List of ingestion runs
        """
        params = {"limit": 50}
        if status:
            params["status"] = status
        response = requests.get(f"{self.base_url}/ingestion/runs", params=params)
        response.raise_for_status()
        return response.json()

    def ingestion_get_stats(self) -> dict:
        """Get overall ingestion statistics.

        Returns:
            Statistics dict
        """
        response = requests.get(f"{self.base_url}/ingestion/stats")
        response.raise_for_status()
        return response.json()

    def ingestion_get_page_audit(self, page_id: int) -> list[dict]:
        """Get audit history for a page.

        Args:
            page_id: BookStack page ID

        Returns:
            List of audit records
        """
        response = requests.get(f"{self.base_url}/ingestion/audit/page/{page_id}")
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # QUERY / SEMANTIC SEARCH
    # ============================================================================

    def query_search(
        self,
        query: str,
        top_k: int = 5,
        use_llm: bool = False,
        use_reranking: bool = False,
        filters: Optional[dict] = None,
    ) -> dict:
        """Execute a semantic search query.

        Args:
            query: Search query
            top_k: Number of results
            use_llm: Whether to generate LLM answer
            use_reranking: Whether to apply reranking
            filters: Optional metadata filters

        Returns:
            Query results with chunks and optional answer
        """
        response = requests.post(
            f"{self.base_url}/query/",
            json={
                "query": query,
                "top_k": top_k,
                "use_llm": use_llm,
                "use_reranking": use_reranking,
                "filters": filters or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def query_batch(self, queries: list[dict]) -> dict:
        """Execute multiple queries in batch.

        Args:
            queries: List of query dicts

        Returns:
            Batch results
        """
        response = requests.post(
            f"{self.base_url}/query/batch",
            json={"queries": queries},
        )
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # CHAT SYSTEM
    # ============================================================================

    def chat_create_session(
        self,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> dict:
        """Create a new chat session.

        Args:
            user_id: Optional user identifier
            title: Optional session title

        Returns:
            Chat session response
        """
        response = requests.post(
            f"{self.base_url}/chat/session",
            json={"user_id": user_id, "title": title},
        )
        response.raise_for_status()
        return response.json()

    async def chat_send_message(
        self,
        session_id: str,
        message: str,
        user_id: Optional[str] = None,
        top_k: int = 5,
        use_reranking: bool = False,
    ) -> dict:
        """Send a message in a chat session.

        Args:
            session_id: Chat session ID
            message: Message text
            user_id: Optional user identifier
            top_k: Number of context chunks
            use_reranking: Whether to apply reranking

        Returns:
            Chat response with answer and sources
        """
        response = requests.post(
            f"{self.base_url}/chat/message",
            json={
                "session_id": session_id,
                "message": message,
                "user_id": user_id,
                "top_k": top_k,
                "use_reranking": use_reranking,
            },
        )
        response.raise_for_status()
        return response.json()

    def chat_get_history(self, session_id: str) -> dict:
        """Get chat history for a session.

        Args:
            session_id: Chat session ID

        Returns:
            Chat history with all messages
        """
        response = requests.get(f"{self.base_url}/chat/session/{session_id}")
        response.raise_for_status()
        return response.json()

    def chat_list_sessions(self, user_id: Optional[str] = None) -> dict:
        """List chat sessions.

        Args:
            user_id: Optional user filter

        Returns:
            Sessions list
        """
        params = {"limit": 50}
        if user_id:
            params["user_id"] = user_id
        response = requests.get(f"{self.base_url}/chat/sessions", params=params)
        response.raise_for_status()
        return response.json()

    def chat_archive_session(self, session_id: str) -> dict:
        """Archive a chat session.

        Args:
            session_id: Chat session ID

        Returns:
            Success message
        """
        response = requests.post(f"{self.base_url}/chat/session/{session_id}/archive")
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # HEALTH CHECKS
    # ============================================================================

    def health_check(self) -> dict:
        """Get comprehensive health check.

        Returns:
            Health status
        """
        response = requests.get(f"{self.base_url}/health/")
        return response.json() if response.status_code == 200 else {"status": "unhealthy"}

    def health_ready(self) -> bool:
        """Check if API is ready.

        Returns:
            True if ready, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/health/ready")
            return response.status_code == 200
        except Exception:
            return False


# ============================================================================
# EXAMPLE 1: Complete Chat Session Flow
# ============================================================================


async def example_complete_chat_flow():
    """Demonstrate a complete multi-turn chat session."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Complete Chat Session Flow")
    print("=" * 80 + "\n")

    client = BookStackRAGClient()

    # Check if API is ready
    if not client.health_ready():
        print("❌ API not ready. Make sure server is running on http://localhost:8001")
        return

    print("✓ API is ready\n")

    # Create chat session
    print("1. Creating chat session...")
    session = client.chat_create_session(
        user_id="example_user",
        title="Technical Questions",
    )
    session_id = session["session_id"]
    print(f"   Session created: {session_id}\n")

    # Turn 1: First question
    print("2. First question: 'How do I configure OAuth2?'")
    response1 = await client.chat_send_message(
        session_id=session_id,
        message="How do I configure OAuth2?",
        user_id="example_user",
        top_k=5,
        use_reranking=True,
    )
    print(f"   AI: {response1['assistant_response'][:150]}...\n")
    print(f"   Sources found: {len(response1['sources'])}")
    print(f"   Response time: {response1.get('request_id', 'N/A')}\n")

    # Turn 2: Follow-up question
    print("3. Follow-up: 'What about token expiration?'")
    response2 = await client.chat_send_message(
        session_id=session_id,
        message="What about token expiration?",
        user_id="example_user",
    )
    print(f"   AI: {response2['assistant_response'][:150]}...\n")

    # Turn 3: Another follow-up
    print("4. Another question: 'How do I refresh tokens?'")
    response3 = await client.chat_send_message(
        session_id=session_id,
        message="How do I refresh tokens?",
        user_id="example_user",
    )
    print(f"   AI: {response3['assistant_response'][:150]}...\n")

    # View full conversation history
    print("5. Retrieving full conversation history...")
    history = client.chat_get_history(session_id)
    print(f"   Total messages in session: {history['message_count']}")
    print("   Conversation:")
    for msg in history["messages"]:
        role = msg["role"].upper()
        content = msg["content"][:80]
        print(f"     [{role}] {content}...")

    print("\n6. Archiving session...")
    client.chat_archive_session(session_id)
    print("   Session archived\n")


# ============================================================================
# EXAMPLE 2: Ingestion Management
# ============================================================================


def example_ingestion_management():
    """Demonstrate ingestion management."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Ingestion Management")
    print("=" * 80 + "\n")

    client = BookStackRAGClient()

    # Check stats
    print("1. Getting ingestion statistics...")
    stats = client.ingestion_get_stats()
    print(f"   Total runs: {stats['total_runs']}")
    print(f"   Completed: {stats['completed_runs']}")
    print(f"   Failed: {stats['failed_runs']}")
    print(f"   Running: {stats['running_runs']}\n")

    # Start full sync
    print("2. Starting full ingestion sync...")
    run = client.ingestion_start_full_sync()
    run_id = run["run_id"]
    print(f"   Run ID: {run_id}")
    print(f"   Status: {run['status']}\n")

    # List runs
    print("3. Listing recent ingestion runs...")
    runs = client.ingestion_list_runs()
    print(f"   Total runs available: {len(runs)}")
    for r in runs[:3]:  # Show first 3
        print(f"     - Run {r['run_id']}: {r['status']} ({r['processed_pages']} pages)")

    print()

    # Get audit for a page
    print("4. Getting audit history for page 42...")
    audits = client.ingestion_get_page_audit(page_id=42)
    if audits:
        print(f"   Found {len(audits)} audit records:")
        for audit in audits[:2]:
            print(f"     - {audit['status']}: {audit['reason']}")
    else:
        print("   No audit records found for this page\n")


# ============================================================================
# EXAMPLE 3: Query with Advanced Features
# ============================================================================


def example_query_advanced():
    """Demonstrate advanced query features."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Advanced Query Features")
    print("=" * 80 + "\n")

    client = BookStackRAGClient()

    # Basic query
    print("1. Basic semantic search...")
    result1 = client.query_search("How do I authenticate users?", top_k=3)
    print(f"   Found {result1['num_results']} relevant chunks")
    print(f"   Top score: {result1['results'][0]['score']:.2f}" if result1["results"] else "   No results")
    print(f"   Latency: {result1['metrics']['total_time_ms']:.0f}ms\n")

    # Query with reranking
    print("2. Query with reranking...")
    result2 = client.query_search(
        "Best practices for API security",
        top_k=5,
        use_reranking=True,
    )
    print(f"   Found {result2['num_results']} chunks")
    print(f"   Reranking time: {result2['metrics'].get('llm_time_ms', 0):.0f}ms\n")

    # Batch queries
    print("3. Batch query processing...")
    batch_result = client.query_batch(
        [
            {"query": "Database configuration"},
            {"query": "Authentication methods", "top_k": 3},
            {"query": "Performance optimization", "use_reranking": True},
        ]
    )
    print(f"   Processed {batch_result['total_queries']} queries")
    print(f"   Errors: {len(batch_result.get('errors', []))}\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


async def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("  BookStack RAG - Complete API Examples")
    print("=" * 80)

    # Example 1: Chat flow
    try:
        await example_complete_chat_flow()
    except Exception as e:
        print(f"❌ Example 1 failed: {e}")

    # Example 2: Ingestion
    try:
        example_ingestion_management()
    except Exception as e:
        print(f"❌ Example 2 failed: {e}")

    # Example 3: Query
    try:
        example_query_advanced()
    except Exception as e:
        print(f"❌ Example 3 failed: {e}")

    print("\n" + "=" * 80)
    print("  Examples completed!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

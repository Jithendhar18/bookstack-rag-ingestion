"""LLM-based answer generation from retrieved chunks."""

from __future__ import annotations

import time
from typing import Optional

from app.config.logging import get_logger
from app.config.settings import Settings
from app.retrieval.retriever import ChunkResult

logger = get_logger(__name__)


class AnswerGenerator:
    """Generate answers using LLM based on retrieved context."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.embedding_provider  # Reuse embedding provider
        self.model = settings.llm_model
        self.max_context_tokens = settings.max_context_tokens
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self._openai_client = None

    def generate(
        self,
        query: str,
        chunks: list[ChunkResult],
        use_stream: bool = False,
    ) -> str:
        """
        Generate answer from query and retrieved chunks.

        Args:
            query: User query
            chunks: List of retrieved chunks
            use_stream: Whether to stream response (if supported)

        Returns:
            Generated answer
        """
        if not chunks:
            return "No relevant information found to answer the question."

        # Build context from chunks
        context = self._build_context(chunks)

        if not context:
            return "Unable to process retrieved information."

        # Generate answer
        if self.provider == "openai":
            return self._generate_openai(query, context, use_stream)
        else:
            return self._generate_local(query, context)

    def _build_context(self, chunks: list[ChunkResult]) -> str:
        """
        Build context string from chunks within token limit.

        Stops adding chunks when max_context_tokens is reached.
        """
        from app.utils.token_utils import count_tokens

        context_parts = []
        token_count = 0

        for chunk in chunks:
            # Include metadata for better context
            part = f"[{chunk.metadata.get('section_path', 'Unknown')}]\n{chunk.chunk_text}"

            part_tokens = count_tokens(part)
            if token_count + part_tokens > self.max_context_tokens:
                logger.warning(
                    "llm.context_truncated",
                    token_count=token_count,
                    max_tokens=self.max_context_tokens,
                    chunks_used=len(context_parts),
                )
                break

            context_parts.append(part)
            token_count += part_tokens

        return "\n\n---\n\n".join(context_parts)

    def _get_openai_client(self):
        """Get or create cached OpenAI client."""
        if self._openai_client is None:
            from openai import OpenAI

            self._openai_client = OpenAI(api_key=self.settings.openai_api_key, timeout=60.0)
        return self._openai_client

    def _generate_openai(self, query: str, context: str, use_stream: bool = False) -> str:
        """Generate answer using OpenAI API with retry and timeout."""
        client = self._get_openai_client()

        system_prompt = """You are a helpful AI assistant that answers questions based ONLY on the provided context.
If the context doesn't contain relevant information to answer the question, say so clearly.
Keep answers concise and well-structured.
Cite relevant sections from the context when helpful."""

        user_prompt = f"""Context:
{context}

Question: {query}

Answer based only on the context provided."""

        logger.debug("llm.generating", model=self.model)

        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                answer = response.choices[0].message.content
                logger.info("llm.answer_generated", chars=len(answer))
                return answer

            except Exception as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                sleep_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "llm.openai_retry",
                    attempt=attempt,
                    sleep_seconds=sleep_seconds,
                    error=str(exc),
                )
                time.sleep(sleep_seconds)

        logger.error("llm.openai_failed", error=str(last_error))
        raise last_error

    def _generate_local(self, query: str, context: str) -> str:
        """Generate answer using local LLM (e.g., Ollama)."""
        logger.info(
            "Local LLM generation not yet implemented. "
            "Please use EMBEDDING_PROVIDER=openai or implement local LLM support."
        )
        return "Local LLM generation not available. Please switch to OpenAI for answer generation."

from __future__ import annotations

import time

from openai import OpenAI

from app.config.settings import Settings


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = self.settings.embedding_provider.strip().lower()
        self._quota_exhausted = False
        self._local_model = None

        if self.provider == "openai":
            self.client = OpenAI(api_key=self.settings.openai_api_key)
        elif self.provider == "local":
            self.client = None
        else:
            raise ValueError("Unsupported embedding provider. Use 'openai' or 'local'.")

    def embed_text(self, text: str) -> list[float]:
        vectors = self.embed_batch([text])
        return vectors[0] if vectors else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.provider == "local":
            return self._embed_batch_local(texts)

        return self._embed_batch_openai(texts)

    def _embed_batch_openai(self, texts: list[str]) -> list[list[float]]:
        if self._quota_exhausted and self.settings.embedding_fail_fast_on_quota:
            raise RuntimeError("OpenAI quota exhausted in this run; failing fast for remaining pages.")

        last_error: Exception | None = None
        for attempt in range(1, self.settings.embedding_max_retries + 1):
            try:
                response = self.client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as exc:  # noqa: BLE001 - intentionally retries provider errors
                if self._is_quota_error(exc):
                    self._quota_exhausted = True
                    if self.settings.embedding_fail_fast_on_quota:
                        raise RuntimeError(
                            "OpenAI quota exceeded. Update billing/key or switch EMBEDDING_PROVIDER=local."
                        ) from exc

                last_error = exc
                if attempt >= self.settings.embedding_max_retries:
                    break
                sleep_seconds = self.settings.retry_backoff_seconds * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)

        if last_error is not None:
            raise last_error

        return []

    def _embed_batch_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            self._local_model = SentenceTransformer(self.settings.local_embedding_model)

        vectors = self._local_model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "insufficient_quota" in message or "quota" in message

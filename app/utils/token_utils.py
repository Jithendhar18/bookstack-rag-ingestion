"""Token counting utilities supporting multiple tokenizers."""

from __future__ import annotations

from functools import lru_cache

import tiktoken

from app.config.logging import get_logger

logger = get_logger(__name__)


class TokenCounter:
    """Token counter with multiple encoding support and fallback."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        """
        Initialize TokenCounter.

        Args:
            encoding_name: Tiktoken encoding name (default: cl100k_base for GPT-4)
        """
        self.encoding_name = encoding_name
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_name)
            self.fallback_ratio = 1.3  # Approximate ratio for fallback
        except Exception as exc:
            logger.warning("tokenizer.load_failed", encoding=encoding_name, error=str(exc))
            self.tokenizer = None
            self.fallback_ratio = 1.3

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Input text

        Returns:
            Token count
        """
        if not text:
            return 0

        if self.tokenizer is not None:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as exc:
                logger.warning("tokenizer.count_failed", error=str(exc))

        # Fallback: character-based approximation
        return self._estimate_tokens(text)

    def encode(self, text: str) -> list[int]:
        """
        Encode text to token IDs.

        Args:
            text: Input text

        Returns:
            Token IDs
        """
        if not text:
            return []

        if self.tokenizer is not None:
            try:
                return self.tokenizer.encode(text)
            except Exception as exc:
                logger.warning("tokenizer.encode_failed", error=str(exc))
                return []

        return []

    def decode(self, token_ids: list[int]) -> str:
        """
        Decode token IDs to text.

        Args:
            token_ids: List of token IDs

        Returns:
            Decoded text
        """
        if not token_ids or self.tokenizer is None:
            return ""

        try:
            return self.tokenizer.decode(token_ids)
        except Exception as exc:
            logger.warning("tokenizer.decode_failed", error=str(exc))
            return ""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Estimate token count using character ratio (fallback).

        Approximate ratio: ~4 characters = 1 token for English text.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return max(1, len(text) // 4)


@lru_cache(maxsize=1)
def get_token_counter(encoding_name: str = "cl100k_base") -> TokenCounter:
    """
    Get cached singleton TokenCounter instance.

    Args:
        encoding_name: Tiktoken encoding name

    Returns:
        TokenCounter instance
    """
    return TokenCounter(encoding_name=encoding_name)


# Convenience functions
def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens in text using cached counter."""
    counter = get_token_counter(encoding_name)
    return counter.count_tokens(text)


def encode_tokens(text: str, encoding_name: str = "cl100k_base") -> list[int]:
    """Encode text to token IDs using cached counter."""
    counter = get_token_counter(encoding_name)
    return counter.encode(text)


def decode_tokens(token_ids: list[int], encoding_name: str = "cl100k_base") -> str:
    """Decode token IDs to text using cached counter."""
    counter = get_token_counter(encoding_name)
    return counter.decode(token_ids)

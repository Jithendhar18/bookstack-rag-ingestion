from __future__ import annotations

from pydantic import BaseModel
import tiktoken


class TextChunk(BaseModel):
    chunk_index: int
    text: str
    start_token: int
    end_token: int


class ChunkingEngine:
    def __init__(self, chunk_size: int = 500, overlap: int = 100, encoding_name: str = "cl100k_base") -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def chunk_text(self, text: str) -> list[TextChunk]:
        if not text.strip():
            return []

        token_ids = self.tokenizer.encode(text)
        if not token_ids:
            return []

        stride = self.chunk_size - self.overlap
        chunks: list[TextChunk] = []

        chunk_index = 0
        for start in range(0, len(token_ids), stride):
            end = min(start + self.chunk_size, len(token_ids))
            chunk_token_ids = token_ids[start:end]
            chunk_text = self.tokenizer.decode(chunk_token_ids).strip()

            if chunk_text:
                chunks.append(
                    TextChunk(
                        chunk_index=chunk_index,
                        text=chunk_text,
                        start_token=start,
                        end_token=end,
                    )
                )
                chunk_index += 1

            if end >= len(token_ids):
                break

        return chunks

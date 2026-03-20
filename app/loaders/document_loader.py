from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.clients.bookstack_client import BookStackClient
from app.config.settings import Settings


class LoadedDocument(BaseModel):
    """Represents a page loaded from BookStack with its content and metadata."""

    page_id: int
    title: str
    book_slug: str | None = None
    chapter_id: int | None = None
    markdown: str
    updated_at: str
    source_url: str


class DocumentLoader:
    """Loads pages from BookStack and converts them to LoadedDocument instances."""

    def __init__(self, bookstack_client: BookStackClient, settings: Settings) -> None:
        self.bookstack_client = bookstack_client
        self.settings = settings

    def load_page(self, page_id: int) -> LoadedDocument:
        """Load a single page from BookStack by its ID."""
        page = self.bookstack_client.get_page(page_id)
        resolved_page_id = int(page.get("id"))
        title = str(page.get("name", "Untitled"))

        # Try markdown first, then fall back to raw_html or html
        markdown = str(page.get("markdown") or "")
        if not markdown.strip():
            markdown = str(page.get("raw_html") or page.get("html") or "")

        updated_at = str(page.get("updated_at") or "")

        # Handle both nested objects and direct fields
        book = page.get("book") or {}
        chapter = page.get("chapter") or {}

        book_slug = self._to_optional_str(
            book.get("slug") if book else None
        ) or self._to_optional_str(page.get("book_slug"))

        chapter_id = self._to_optional_int(
            chapter.get("id") if chapter else None
        ) or self._to_optional_int(page.get("chapter_id"))

        relative_url = self._to_optional_str(page.get("url"))
        source_url = (
            f"{self.settings.bookstack_url.rstrip('/')}{relative_url}"
            if relative_url
            else self.settings.bookstack_url
        )

        return LoadedDocument(
            page_id=resolved_page_id,
            title=title,
            book_slug=book_slug,
            chapter_id=chapter_id,
            markdown=markdown,
            updated_at=updated_at,
            source_url=source_url,
        )

    @staticmethod
    def _to_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

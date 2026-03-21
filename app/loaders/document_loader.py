from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.clients.bookstack_client import BookStackClient
from app.config.settings import Settings


class LoadedDocument(BaseModel):
    page_id: int
    title: str
    book_slug: str | None = None
    chapter_id: int | None = None
    markdown: str
    html: str
    updated_at: str
    source_url: str


class DocumentLoader:
    def __init__(self, bookstack_client: BookStackClient, settings: Settings) -> None:
        self.bookstack_client = bookstack_client
        self.settings = settings

    def load_page(self, page_id: int) -> LoadedDocument:
        page = self.bookstack_client.get_page(page_id)

        resolved_page_id = int(page.get("id"))
        title = str(page.get("name", "Untitled"))
        markdown = str(page.get("markdown") or "")
        html = str(page.get("html") or "")
        updated_at = str(page.get("updated_at") or "")

        book = page.get("book") or {}
        chapter = page.get("chapter") or {}

        book_slug = self._to_optional_str(book.get("slug") or page.get("book_slug"))
        chapter_id = self._to_optional_int(chapter.get("id") or page.get("chapter_id"))
        page_slug = self._to_optional_str(page.get("slug"))

        base = self.settings.bookstack_url.rstrip("/")
        relative_url = self._to_optional_str(page.get("url"))
        if relative_url:
            source_url = f"{base}{relative_url}"
        elif book_slug and page_slug:
            source_url = f"{base}/books/{book_slug}/page/{page_slug}"
        else:
            source_url = f"{base}/link/{resolved_page_id}"

        return LoadedDocument(
            page_id=resolved_page_id,
            title=title,
            book_slug=book_slug,
            chapter_id=chapter_id,
            markdown=markdown,
            html=html,
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

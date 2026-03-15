from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.clients.bookstack_client import BookStackClient
from app.db.metadata_store import MetadataStore


class DocumentSyncService:
    def __init__(self, bookstack_client: BookStackClient, metadata_store: MetadataStore) -> None:
        self.bookstack_client = bookstack_client
        self.metadata_store = metadata_store

    def get_pages_to_sync(self, pages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        pages = pages if pages is not None else self.bookstack_client.get_pages()
        candidates: list[dict[str, Any]] = []

        for page in pages:
            page_id_raw = page.get("id")
            updated_at = str(page.get("updated_at") or "")

            if page_id_raw is None or not updated_at:
                continue

            try:
                page_id = int(page_id_raw)
            except (TypeError, ValueError):
                continue

            if self.metadata_store.is_page_stale(page_id=page_id, updated_at_raw=updated_at):
                candidates.append(page)

        return candidates

    def classify_pages(self, pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[SyncDecision]]:
        candidates: list[dict[str, Any]] = []
        decisions: list[SyncDecision] = []

        for page in pages:
            page_id_raw = page.get("id")
            updated_at_raw = str(page.get("updated_at") or "")

            if page_id_raw is None:
                continue

            try:
                page_id = int(page_id_raw)
            except (TypeError, ValueError):
                continue

            existing = self.metadata_store.get_document(page_id)
            remote_updated_at = self._parse_timestamp(updated_at_raw)

            if existing is None:
                candidates.append(page)
                decisions.append(
                    SyncDecision(
                        page_id=page_id,
                        status="NEW",
                        reason="not_found_in_local_metadata",
                        source_updated_at=remote_updated_at,
                        local_updated_at=None,
                    )
                )
                continue

            local_updated_at = existing.get("updated_at")
            if not isinstance(local_updated_at, datetime):
                candidates.append(page)
                decisions.append(
                    SyncDecision(
                        page_id=page_id,
                        status="UPDATED",
                        reason="local_updated_at_missing_or_invalid",
                        source_updated_at=remote_updated_at,
                        local_updated_at=None,
                    )
                )
                continue

            if remote_updated_at > local_updated_at:
                candidates.append(page)
                decisions.append(
                    SyncDecision(
                        page_id=page_id,
                        status="UPDATED",
                        reason="remote_updated_at_is_newer",
                        source_updated_at=remote_updated_at,
                        local_updated_at=local_updated_at,
                    )
                )
            else:
                decisions.append(
                    SyncDecision(
                        page_id=page_id,
                        status="UNCHANGED",
                        reason="remote_updated_at_not_newer",
                        source_updated_at=remote_updated_at,
                        local_updated_at=local_updated_at,
                    )
                )

        return candidates, decisions

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        normalized = value.strip()
        if not normalized:
            return datetime.now(timezone.utc)
        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")

        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def extract_page_ids(pages: list[dict[str, Any]]) -> set[int]:
        page_ids: set[int] = set()
        for page in pages:
            raw_id = page.get("id")
            if raw_id is None:
                continue
            try:
                page_ids.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        return page_ids

    @staticmethod
    def as_batches(pages: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        return [pages[index : index + batch_size] for index in range(0, len(pages), batch_size)]


@dataclass(frozen=True)
class SyncDecision:
    page_id: int
    status: str
    reason: str
    source_updated_at: datetime | None
    local_updated_at: datetime | None

from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config.settings import Settings


class BookStackClient:
    """HTTP client for the BookStack REST API.

    Handles authentication, rate limiting, pagination, and retries.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = settings.bookstack_timeout
        self.session = requests.Session()
        self.session.headers.update(self.settings.bookstack_auth_header)
        self._request_interval_seconds = (
            1.0 / self.settings.bookstack_requests_per_second
            if self.settings.bookstack_requests_per_second > 0
            else 0.0
        )
        self._last_request_time = 0.0
        self._configure_retries()

    def _configure_retries(self) -> None:
        """Configure retry strategy on the HTTP session."""
        retry = Retry(
            total=self.settings.bookstack_max_retries,
            backoff_factor=self.settings.retry_backoff_seconds,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _apply_rate_limit(self) -> None:
        """Sleep if necessary to respect the configured request rate."""
        if self._request_interval_seconds <= 0:
            return

        elapsed = time.monotonic() - self._last_request_time
        wait_seconds = self._request_interval_seconds - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an authenticated GET request to BookStack."""
        url = f"{self.settings.bookstack_api_base}{endpoint}"
        self._apply_rate_limit()
        response = self.session.get(url, params=params, timeout=self.timeout)
        self._last_request_time = time.monotonic()
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected BookStack response type for {endpoint}: {type(payload)}")

        return payload

    def _get_paginated(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a paginated BookStack endpoint."""
        merged_params = params.copy() if params else {}
        count = 100
        offset = 0
        results: list[dict[str, Any]] = []

        while True:
            page_params = {**merged_params, "count": count, "offset": offset}
            payload = self._get(endpoint=endpoint, params=page_params)

            data = payload.get("data", [])
            if not isinstance(data, list):
                raise ValueError(f"Expected list in 'data' for endpoint {endpoint}")

            results.extend(data)

            total = payload.get("total")
            if isinstance(total, int):
                if offset + count >= total:
                    break
            elif len(data) < count:
                break

            if not data:
                break

            offset += count

        return results

    def get_pages(self) -> list[dict[str, Any]]:
        """Retrieve all pages from BookStack."""
        return self._get_paginated("/pages")

    def get_page(self, page_id: int) -> dict[str, Any]:
        """Retrieve a single page by ID."""
        return self._get(f"/pages/{page_id}")

    def get_books(self) -> list[dict[str, Any]]:
        """Retrieve all books from BookStack."""
        return self._get_paginated("/books")

    def get_chapters(self) -> list[dict[str, Any]]:
        """Retrieve all chapters from BookStack."""
        return self._get_paginated("/chapters")

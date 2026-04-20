"""
HTTP client for the Swiss Truth REST API.

Supports both sync (requests) and async (aiohttp, optional) transports.
"""
from __future__ import annotations

from typing import Any, Optional

import requests


_DEFAULT_BASE_URL = "https://swisstruth.org"


class SwissTruthClient:
    """Thin HTTP client for the Swiss Truth API."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = "",
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "swiss-truth-langchain/0.2.0",
        })
        if api_key:
            self._session.headers["X-Swiss-Truth-Key"] = api_key

    # ── Sync helpers ──────────────────────────────────────────────────────

    def get(self, path: str, **params: Any) -> Any:
        r = self._session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> Any:
        r = self._session.post(
            f"{self.base_url}{path}", json=body, timeout=self.timeout + 30
        )
        r.raise_for_status()
        return r.json()

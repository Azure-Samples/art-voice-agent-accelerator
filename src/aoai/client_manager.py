"""Centralized Azure OpenAI client lifecycle management."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from utils.ml_logging import get_logger

from .client import create_azure_openai_client

logger = get_logger(__name__)


class AoaiClientManager:
    """Own Azure OpenAI client creation, caching, and refresh operations."""

    def __init__(
        self,
        *,
        session_manager: Optional[Any] = None,
        factory: Optional[Callable[[], Any]] = None,
        initial_client: Optional[Any] = None,
    ) -> None:
        self._session_manager = session_manager
        self._factory = factory or create_azure_openai_client
        self._client: Optional[Any] = initial_client
        self._lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._last_refresh_at: Optional[datetime] = (
            datetime.now(timezone.utc) if initial_client is not None else None
        )
        self._refresh_count: int = 1 if initial_client is not None else 0

    async def get_client(self, *, session_id: Optional[str] = None) -> Any:
        """Return the cached client, creating it on first request."""
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is None:
                self._client = await self._build_client()
                await self._set_session_metadata(session_id, "aoai.last_refresh_at", self._last_refresh_at)
        return self._client

    async def refresh_after_auth_failure(self, *, session_id: Optional[str] = None) -> Any:
        """Rebuild the client when authentication fails and share refreshed instance."""
        async with self._refresh_lock:
            self._client = await self._build_client(reason="auth_failure", session_id=session_id)
            await self._set_session_metadata(session_id, "aoai.last_refresh_at", self._last_refresh_at)
        return self._client

    async def _build_client(self, *, reason: str = "initial", session_id: Optional[str] = None) -> Any:
        """Invoke factory in a worker thread and capture refresh diagnostics."""
        logger.info(
            "Building Azure OpenAI client",
            extra={
                "reason": reason,
                "session_id": session_id,
                "refresh_count": self._refresh_count,
            },
        )
        client = await asyncio.to_thread(self._factory)
        self._last_refresh_at = datetime.now(timezone.utc)
        self._refresh_count += 1
        logger.info(
            "Azure OpenAI client ready",
            extra={
                "reason": reason,
                "session_id": session_id,
                "refresh_count": self._refresh_count,
                "refreshed_at": self._last_refresh_at.isoformat(),
            },
        )
        return client

    async def _set_session_metadata(self, session_id: Optional[str], key: str, value: Any) -> None:
        if not session_id or not self._session_manager:
            return
        try:
            await self._session_manager.set_metadata(session_id, key, value)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Failed to set session metadata",
                extra={
                    "session_id": session_id,
                    "metadata_key": key,
                    "error": str(exc),
                },
            )

    @property
    def last_refresh_at(self) -> Optional[datetime]:
        return self._last_refresh_at

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

"""Centralized Azure OpenAI client lifecycle management with telemetry."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from opentelemetry import trace
from utils.ml_logging import get_logger

from .client import create_azure_openai_client, AzureOpenAIManager, _is_aoai_tracing_enabled

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class AoaiClientManager:
    """Advanced Azure OpenAI client creation, caching, refresh, and telemetry operations."""

    def __init__(
        self,
        *,
        session_manager: Optional[Any] = None,
        factory: Optional[Callable[[], Any]] = None,
        initial_client: Optional[Any] = None,
        call_connection_id: Optional[str] = None,
        session_id: Optional[str] = None,
        enable_telemetry: Optional[bool] = None,
    ) -> None:
        self._session_manager = session_manager
        self._factory = factory or create_azure_openai_client
        self._client: Optional[Any] = initial_client
        self._manager: Optional[AzureOpenAIManager] = None
        self._lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._last_refresh_at: Optional[datetime] = (
            datetime.now(timezone.utc) if initial_client is not None else None
        )
        self._refresh_count: int = 1 if initial_client is not None else 0
        self._call_connection_id = call_connection_id
        self._session_id = session_id
        self._enable_telemetry = enable_telemetry if enable_telemetry is not None else _is_aoai_tracing_enabled()
        
        # Telemetry counters
        self._total_requests = 0
        self._total_errors = 0
        self._total_rate_limits = 0

    async def get_client(self, *, session_id: Optional[str] = None) -> Any:
        """Return the cached client, creating it on first request with telemetry."""
        start_time = time.time()
        
        with tracer.start_as_current_span(
            "aoai_client_manager.get_client",
            attributes={
                "session_id": session_id or self._session_id,
                "call_connection_id": self._call_connection_id,
                "client_exists": self._client is not None,
            }
        ) as span:
            try:
                if self._client is not None:
                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_attribute("cache_hit", True)
                    return self._client

                async with self._lock:
                    if self._client is None:
                        self._client = await self._build_client()
                        await self._set_session_metadata(
                            session_id, "aoai.last_refresh_at", self._last_refresh_at
                        )
                
                duration = time.time() - start_time
                span.set_attribute("duration_ms", duration * 1000)
                span.set_attribute("cache_hit", False)
                
                logger.info(
                    "Azure OpenAI client retrieved",
                    extra={
                        "duration_ms": duration * 1000,
                        "cache_hit": False,
                        "session_id": session_id or self._session_id,
                        "call_connection_id": self._call_connection_id,
                        "refresh_count": self._refresh_count,
                    }
                )
                
                return self._client
                
            except Exception as e:
                duration = time.time() - start_time
                span.record_exception(e)
                span.set_attribute("duration_ms", duration * 1000)
                span.set_attribute("error.type", type(e).__name__)
                
                self._total_errors += 1
                
                logger.error(
                    "Failed to get Azure OpenAI client",
                    extra={
                        "error": str(e),
                        "duration_ms": duration * 1000,
                        "session_id": session_id or self._session_id,
                        "call_connection_id": self._call_connection_id,
                        "total_errors": self._total_errors,
                    }
                )
                raise

    async def refresh_after_auth_failure(self, *, session_id: Optional[str] = None) -> Any:
        """Rebuild the client when authentication fails with telemetry tracking."""
        start_time = time.time()
        
        with tracer.start_as_current_span(
            "aoai_client_manager.refresh_after_auth_failure",
            attributes={
                "session_id": session_id or self._session_id,
                "call_connection_id": self._call_connection_id,
                "refresh_count": self._refresh_count,
            }
        ) as span:
            try:
                async with self._refresh_lock:
                    self._client = await self._build_client(
                        reason="auth_failure", session_id=session_id
                    )
                    await self._set_session_metadata(
                        session_id, "aoai.last_refresh_at", self._last_refresh_at
                    )
                
                duration = time.time() - start_time
                span.set_attribute("duration_ms", duration * 1000)
                
                logger.info(
                    "Azure OpenAI client refreshed after auth failure",
                    extra={
                        "duration_ms": duration * 1000,
                        "session_id": session_id or self._session_id,
                        "call_connection_id": self._call_connection_id,
                        "refresh_count": self._refresh_count,
                    }
                )
                
                return self._client
                
            except Exception as e:
                duration = time.time() - start_time
                span.record_exception(e)
                span.set_attribute("duration_ms", duration * 1000)
                
                self._total_errors += 1
                
                logger.error(
                    "Failed to refresh Azure OpenAI client after auth failure",
                    extra={
                        "error": str(e),
                        "duration_ms": duration * 1000,
                        "session_id": session_id or self._session_id,
                        "call_connection_id": self._call_connection_id,
                        "total_errors": self._total_errors,
                    }
                )
                raise

    async def get_manager(self, *, session_id: Optional[str] = None) -> AzureOpenAIManager:
        """Get or create an AzureOpenAIManager instance with telemetry."""
        if self._manager is not None:
            return self._manager
        
        # Ensure we have a client first
        await self.get_client(session_id=session_id)
        
        self._manager = AzureOpenAIManager(
            call_connection_id=self._call_connection_id,
            session_id=session_id or self._session_id,
            enable_tracing=self._enable_telemetry,
        )
        
        return self._manager
    
    def get_telemetry_stats(self) -> dict:
        """Get telemetry statistics for this client manager."""
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "total_rate_limits": self._total_rate_limits,
            "refresh_count": self._refresh_count,
            "last_refresh_at": self._last_refresh_at.isoformat() if self._last_refresh_at else None,
            "session_id": self._session_id,
            "call_connection_id": self._call_connection_id,
        }
    
    def increment_request_counter(self):
        """Increment request counter for telemetry."""
        self._total_requests += 1
    
    def increment_rate_limit_counter(self):
        """Increment rate limit counter for telemetry."""
        self._total_rate_limits += 1

    async def _build_client(self, *, reason: str = "initial", session_id: Optional[str] = None) -> Any:
        """Invoke factory in a worker thread and capture refresh diagnostics with telemetry."""
        start_time = time.time()
        
        with tracer.start_as_current_span(
            "aoai_client_manager.build_client",
            attributes={
                "reason": reason,
                "session_id": session_id or self._session_id,
                "call_connection_id": self._call_connection_id,
                "refresh_count": self._refresh_count,
            }
        ) as span:
            try:
                logger.info(
                    "Building Azure OpenAI client",
                    extra={
                        "reason": reason,
                        "session_id": session_id or self._session_id,
                        "refresh_count": self._refresh_count,
                        "call_connection_id": self._call_connection_id,
                    },
                )
                
                client = await asyncio.to_thread(self._factory)
                self._last_refresh_at = datetime.now(timezone.utc)
                self._refresh_count += 1
                
                duration = time.time() - start_time
                span.set_attribute("duration_ms", duration * 1000)
                span.set_attribute("refresh_count", self._refresh_count)
                
                logger.info(
                    "Azure OpenAI client ready",
                    extra={
                        "reason": reason,
                        "session_id": session_id or self._session_id,
                        "refresh_count": self._refresh_count,
                        "refreshed_at": self._last_refresh_at.isoformat(),
                        "duration_ms": duration * 1000,
                        "call_connection_id": self._call_connection_id,
                    },
                )
                
                return client
                
            except Exception as e:
                duration = time.time() - start_time
                span.record_exception(e)
                span.set_attribute("duration_ms", duration * 1000)
                
                self._total_errors += 1
                
                logger.error(
                    "Failed to build Azure OpenAI client",
                    extra={
                        "error": str(e),
                        "reason": reason,
                        "session_id": session_id or self._session_id,
                        "duration_ms": duration * 1000,
                        "call_connection_id": self._call_connection_id,
                        "total_errors": self._total_errors,
                    },
                )
                raise

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

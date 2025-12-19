"""Lightweight on-demand resource provider used when pooling adds overhead."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class AllocationTier(Enum):
    """Resource allocation tiers for different latency requirements."""

    DEDICATED = "dedicated"  # Per-session, 0ms latency
    WARM = "warm"  # Pre-warmed pool, <50ms latency
    COLD = "cold"  # On-demand creation, <200ms latency


@dataclass
class _ProviderMetrics:
    """Minimal metrics payload for compatibility with diagnostics."""

    allocations_total: int = 0
    allocations_cached: int = 0
    allocations_new: int = 0
    active_sessions: int = 0


class OnDemandResourcePool(Generic[T]):
    """Simple async factory that mimics the AsyncPool surface without queues."""

    def __init__(
        self,
        *,
        factory: Callable[[], Awaitable[T]],
        session_awareness: bool,
        name: str,
    ) -> None:
        self._factory = factory
        self._session_awareness = session_awareness
        self._name = name
        self._ready = asyncio.Event()
        self._session_cache: dict[str, T] = {}
        self._lock = asyncio.Lock()
        self._metrics = _ProviderMetrics()

    async def prepare(self) -> None:
        """Mark the provider as ready; no prewarming performed."""
        self._ready.set()

    async def shutdown(self) -> None:
        """Release cached session resources."""
        async with self._lock:
            self._session_cache.clear()
            self._metrics.active_sessions = 0
        self._ready.clear()

    async def acquire(self, timeout: float | None = None) -> T:  # noqa: ARG002
        """Return a fresh resource instance."""
        self._metrics.allocations_total += 1
        self._metrics.allocations_new += 1
        return await self._factory()

    async def release(self, resource: T | None) -> None:  # noqa: ARG002
        """Release is a no-op for on-demand resources."""
        return None

    async def acquire_for_session(
        self, session_id: str | None, timeout: float | None = None  # noqa: ARG002
    ) -> tuple[T, AllocationTier]:
        """Return a cached resource for the session or create a new one."""
        if not self._session_awareness or not session_id:
            resource = await self.acquire()
            return resource, AllocationTier.COLD

        async with self._lock:
            resource = self._session_cache.get(session_id)
            if resource is not None:
                # Validate cached resource is still ready
                if getattr(resource, "is_ready", True):
                    self._metrics.allocations_total += 1
                    self._metrics.allocations_cached += 1
                    return resource, AllocationTier.DEDICATED
                else:
                    # Cached resource is no longer valid, remove it
                    self._session_cache.pop(session_id, None)

            resource = await self._factory()
            self._session_cache[session_id] = resource
            self._metrics.allocations_total += 1
            self._metrics.allocations_new += 1
            self._metrics.active_sessions = len(self._session_cache)
            return resource, AllocationTier.COLD

    async def release_for_session(
        self, session_id: str | None, resource: T | None = None  # noqa: ARG002
    ) -> bool:
        """Remove the cached resource for the given session if present.

        Clears any session-specific state on the resource before discarding.
        """
        if not self._session_awareness or not session_id:
            # Clear session state before discard
            if resource is not None and hasattr(resource, "clear_session_state"):
                try:
                    resource.clear_session_state()
                except Exception:
                    pass
            return True

        async with self._lock:
            removed = self._session_cache.pop(session_id, None)
            self._metrics.active_sessions = len(self._session_cache)
            if removed is not None:
                # Clear session state on the cached resource
                if hasattr(removed, "clear_session_state"):
                    try:
                        removed.clear_session_state()
                    except Exception:
                        pass
            return removed is not None

    def snapshot(self) -> dict[str, Any]:
        """Return a lightweight status map for logging/diagnostics."""
        metrics = asdict(self._metrics)
        metrics["timestamp"] = time.time()
        return {
            "name": self._name,
            "ready": self._ready.is_set(),
            "session_awareness": self._session_awareness,
            "active_sessions": len(self._session_cache),
            "metrics": metrics,
        }

    @property
    def session_awareness_enabled(self) -> bool:
        return self._session_awareness

    @property
    def active_sessions(self) -> int:
        return len(self._session_cache)

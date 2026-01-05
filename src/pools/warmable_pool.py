"""
WarmableResourcePool - Resource pool with optional pre-warming and session awareness.

Drop-in replacement for OnDemandResourcePool with configurable warm pool behavior.
When warm_pool_size=0 (default), behaves identically to OnDemandResourcePool.

Allocation Tiers:
1. DEDICATED - Per-session cached resource (0ms latency)
2. WARM - Pre-created resource from pool (<50ms latency)
3. COLD - On-demand factory call (~200ms latency)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Generic, TypeVar

from utils.ml_logging import get_logger

from src.pools.on_demand_pool import AllocationTier

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class WarmablePoolMetrics:
    """Pool metrics for monitoring and diagnostics."""

    allocations_total: int = 0
    allocations_dedicated: int = 0
    allocations_warm: int = 0
    allocations_cold: int = 0
    active_sessions: int = 0
    warm_pool_size: int = 0
    warmup_cycles: int = 0
    warmup_failures: int = 0
    warmup_timeouts: int = 0
    warmup_retries: int = 0
    last_warmup_error: str | None = None


class WarmableResourcePool(Generic[T]):
    """
    Resource pool with optional pre-warming and session awareness.

    When warm_pool_size > 0, maintains a queue of pre-warmed resources for
    low-latency allocation. Background task replenishes the pool periodically.

    When warm_pool_size = 0 (default), behaves like OnDemandResourcePool.

    Features robust failure handling with timeouts, retries, and graceful
    degradation to ensure application stability even when warmup fails.

    Args:
        factory: Async callable that creates a new resource instance.
        name: Pool name for logging and diagnostics.
        warm_pool_size: Number of pre-warmed resources to maintain (0 = disabled).
        enable_background_warmup: Run background task to maintain pool level.
        warmup_interval_sec: Interval between background warmup cycles.
        session_awareness: Enable per-session resource caching.
        session_max_age_sec: Max age for cached session resources (cleanup).
        warm_fn: Optional async function to warm a resource after creation.
                 Should return True on success, False on failure.
        warmup_timeout_sec: Maximum time allowed per warmup attempt (default: 10s).
        max_warmup_retries: Number of retry attempts for failed warmups (default: 2).
    """

    def __init__(
        self,
        *,
        factory: Callable[[], Awaitable[T]],
        name: str,
        warm_pool_size: int = 0,
        enable_background_warmup: bool = False,
        warmup_interval_sec: float = 30.0,
        session_awareness: bool = False,
        session_max_age_sec: float = 1800.0,
        warm_fn: Callable[[T], Awaitable[bool]] | None = None,
        warmup_timeout_sec: float = 10.0,
        max_warmup_retries: int = 2,
    ) -> None:
        self._factory = factory
        self._name = name
        self._warm_pool_size = warm_pool_size
        self._enable_background_warmup = enable_background_warmup
        self._warmup_interval_sec = warmup_interval_sec
        self._session_awareness = session_awareness
        self._session_max_age_sec = session_max_age_sec
        self._warm_fn = warm_fn
        self._warmup_timeout_sec = warmup_timeout_sec
        self._max_warmup_retries = max_warmup_retries

        # State
        self._ready = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._warm_queue: asyncio.Queue[T] = asyncio.Queue(maxsize=max(1, warm_pool_size))
        self._session_cache: dict[str, tuple[T, float]] = {}  # session_id -> (resource, last_used)
        self._lock = asyncio.Lock()
        self._metrics = WarmablePoolMetrics()
        self._background_task: asyncio.Task[None] | None = None

    async def prepare(self) -> None:
        """
        Initialize the pool and optionally pre-warm resources.

        If warm_pool_size > 0, attempts to create initial warm resources.
        Failures during warmup do NOT prevent pool initialization - the pool
        will gracefully degrade to on-demand allocation.
        
        If enable_background_warmup, starts background maintenance task
        which will continue attempting to fill the warm pool.
        """
        warmup_success = False
        if self._warm_pool_size > 0:
            logger.debug(f"[{self._name}] Pre-warming {self._warm_pool_size} resources...")
            try:
                # Timeout entire warmup phase to prevent startup hang
                added = await asyncio.wait_for(
                    self._fill_warm_pool(),
                    timeout=self._warmup_timeout_sec * self._warm_pool_size + 10.0
                )
                warmup_success = added > 0
                if not warmup_success:
                    logger.warning(
                        f"[{self._name}] Initial warmup produced 0 resources. "
                        f"Pool will use on-demand allocation."
                    )
            except asyncio.TimeoutError:
                logger.error(
                    f"[{self._name}] Initial warmup timed out. "
                    f"Pool will use on-demand allocation and background warmup will retry."
                )
            except Exception as e:
                logger.error(
                    f"[{self._name}] Initial warmup failed: {e}. "
                    f"Pool will use on-demand allocation.",
                    exc_info=True
                )

        if self._enable_background_warmup and self._warm_pool_size > 0:
            self._background_task = asyncio.create_task(
                self._background_warmup_loop(),
                name=f"{self._name}-warmup",
            )
            logger.debug(
                f"[{self._name}] Started background warmup (interval={self._warmup_interval_sec}s)"
            )

        # Always mark ready - graceful degradation
        self._ready.set()
        
        ready_count = self._warm_queue.qsize()
        if ready_count == self._warm_pool_size:
            logger.info(
                f"[{self._name}] Pool ready with {ready_count}/{self._warm_pool_size} warm resources"
            )
        elif ready_count > 0:
            logger.warning(
                f"[{self._name}] Pool ready with partial warmup: {ready_count}/{self._warm_pool_size} resources. "
                f"Background warmup will continue filling."
            )
        else:
            logger.warning(
                f"[{self._name}] Pool ready in on-demand mode (warmup failed). "
                f"Expect higher latency until background warmup succeeds."
            )

    async def shutdown(self) -> None:
        """Stop background tasks and clear all resources."""
        self._shutdown_event.set()

        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await asyncio.wait_for(self._background_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

        async with self._lock:
            # Clear warm pool
            while not self._warm_queue.empty():
                try:
                    self._warm_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Clear session cache
            self._session_cache.clear()
            self._metrics.active_sessions = 0
            self._metrics.warm_pool_size = 0

        self._ready.clear()
        logger.debug(f"[{self._name}] Pool shutdown complete")

    async def acquire(self, timeout: float | None = None) -> T:
        """
        Acquire a resource from the pool.

        Priority: warm pool -> cold (factory).
        """
        self._metrics.allocations_total += 1

        # Try warm pool first (non-blocking)
        try:
            resource = self._warm_queue.get_nowait()
            self._metrics.allocations_warm += 1
            self._metrics.warm_pool_size = self._warm_queue.qsize()
            logger.debug(f"[{self._name}] Acquired WARM resource")
            return resource
        except asyncio.QueueEmpty:
            pass

        # Fall back to cold creation
        resource = await self._create_warmed_resource()
        self._metrics.allocations_cold += 1
        logger.debug(f"[{self._name}] Acquired COLD resource")
        return resource

    async def release(self, resource: T | None) -> None:
        """
        Release a resource back to the pool.

        Clears any session-specific state before returning to warm pool.
        If warm pool has space, returns resource to pool. Otherwise discards.
        """
        if resource is None:
            return

        # Clear session state before potentially returning to warm pool
        if hasattr(resource, "clear_session_state"):
            try:
                resource.clear_session_state()
            except Exception as e:
                logger.warning(f"[{self._name}] Failed to clear session state on release: {e}")

        # Try to return to warm pool if there's space
        if self._warm_pool_size > 0:
            try:
                self._warm_queue.put_nowait(resource)
                self._metrics.warm_pool_size = self._warm_queue.qsize()
                return
            except asyncio.QueueFull:
                pass

        # Otherwise discard (resource will be garbage collected)

    async def acquire_for_session(
        self, session_id: str | None, timeout: float | None = None
    ) -> tuple[T, AllocationTier]:
        """
        Acquire a resource for a specific session.

        Priority: session cache (DEDICATED) -> warm pool (WARM) -> factory (COLD).
        """
        if not self._session_awareness or not session_id:
            resource = await self.acquire(timeout=timeout)
            tier = (
                AllocationTier.WARM
                if self._metrics.allocations_warm > self._metrics.allocations_cold
                else AllocationTier.COLD
            )
            return resource, tier

        async with self._lock:
            # Check session cache first
            cached = self._session_cache.get(session_id)
            if cached is not None:
                resource, _ = cached
                # Validate resource is still ready
                if getattr(resource, "is_ready", True):
                    self._session_cache[session_id] = (resource, time.time())
                    self._metrics.allocations_total += 1
                    self._metrics.allocations_dedicated += 1
                    logger.debug(
                        f"[{self._name}] Acquired DEDICATED resource for session {session_id[:8]}..."
                    )
                    return resource, AllocationTier.DEDICATED
                else:
                    # Stale resource, remove from cache
                    self._session_cache.pop(session_id, None)

        # Not in session cache - acquire from pool
        resource = await self.acquire(timeout=timeout)

        # Cache for session
        async with self._lock:
            self._session_cache[session_id] = (resource, time.time())
            self._metrics.active_sessions = len(self._session_cache)

        # Determine tier based on where resource came from
        # (acquire() already updated warm/cold metrics)
        tier = (
            AllocationTier.WARM
            if self._warm_queue.qsize() < self._warm_pool_size
            else AllocationTier.COLD
        )
        return resource, tier

    async def release_for_session(self, session_id: str | None, resource: T | None = None) -> bool:
        """
        Release session-bound resource and remove from cache.

        Clears any session-specific state on the resource before discarding
        to prevent state leakage across sessions.

        Returns True if session was found and removed.
        """
        if not self._session_awareness or not session_id:
            # Clear session state before release
            if resource is not None and hasattr(resource, "clear_session_state"):
                try:
                    resource.clear_session_state()
                except Exception as e:
                    logger.warning(f"[{self._name}] Failed to clear session state: {e}")
            await self.release(resource)
            return True

        async with self._lock:
            removed = self._session_cache.pop(session_id, None)
            self._metrics.active_sessions = len(self._session_cache)

            if removed is not None:
                cached_resource, _ = removed
                # Clear session state on the cached resource
                if hasattr(cached_resource, "clear_session_state"):
                    try:
                        cached_resource.clear_session_state()
                    except Exception as e:
                        logger.warning(f"[{self._name}] Failed to clear session state: {e}")
                logger.debug(f"[{self._name}] Released session resource for {session_id[:8]}...")
                # Don't return session resources to warm pool - they may have state
                return True
            return False

    def snapshot(self) -> dict[str, Any]:
        """Return current pool status for diagnostics."""
        metrics = asdict(self._metrics)
        metrics["timestamp"] = time.time()
        return {
            "name": self._name,
            "ready": self._ready.is_set(),
            "warm_pool_size": self._warm_queue.qsize(),
            "warm_pool_target": self._warm_pool_size,
            "session_awareness": self._session_awareness,
            "active_sessions": len(self._session_cache),
            "background_warmup": self._enable_background_warmup,
            "metrics": metrics,
        }

    @property
    def session_awareness_enabled(self) -> bool:
        return self._session_awareness

    @property
    def active_sessions(self) -> int:
        return len(self._session_cache)

    # ---------- Internal Methods ----------

    async def _create_warmed_resource(self) -> T:
        """Create a new resource and optionally warm it with timeout and retry."""
        resource = await self._factory()

        if self._warm_fn is None:
            return resource

        # Attempt warmup with retries
        for attempt in range(self._max_warmup_retries + 1):
            try:
                # Apply timeout to warmup operation
                success = await asyncio.wait_for(
                    self._warm_fn(resource),
                    timeout=self._warmup_timeout_sec
                )
                
                if success:
                    if attempt > 0:
                        logger.info(f"[{self._name}] Warmup succeeded on retry {attempt}")
                    return resource
                else:
                    error_msg = f"Warmup function returned False (attempt {attempt + 1}/{self._max_warmup_retries + 1})"
                    logger.warning(f"[{self._name}] {error_msg}")
                    self._metrics.last_warmup_error = error_msg
                    
            except asyncio.TimeoutError:
                error_msg = f"Warmup timed out after {self._warmup_timeout_sec}s (attempt {attempt + 1}/{self._max_warmup_retries + 1})"
                logger.warning(f"[{self._name}] {error_msg}")
                self._metrics.warmup_timeouts += 1
                self._metrics.last_warmup_error = error_msg
                
            except Exception as e:
                error_msg = f"Warmup failed with {type(e).__name__}: {e} (attempt {attempt + 1}/{self._max_warmup_retries + 1})"
                logger.warning(f"[{self._name}] {error_msg}")
                self._metrics.last_warmup_error = error_msg
            
            # Retry with exponential backoff (except on last attempt)
            if attempt < self._max_warmup_retries:
                self._metrics.warmup_retries += 1
                backoff = min(2 ** attempt * 0.5, 5.0)  # 0.5s, 1s, 2s... max 5s
                logger.debug(f"[{self._name}] Retrying warmup in {backoff}s...")
                await asyncio.sleep(backoff)
        
        # All retries exhausted
        self._metrics.warmup_failures += 1
        logger.warning(
            f"[{self._name}] All warmup attempts failed. Resource created but not warmed. "
            f"This may cause higher latency on first use."
        )
        return resource

    async def _fill_warm_pool(self) -> int:
        """Fill warm pool up to target size. Returns number of resources added."""
        added = 0
        target = self._warm_pool_size - self._warm_queue.qsize()

        for i in range(target):
            if self._shutdown_event.is_set():
                break
            try:
                # Add overall timeout per resource (factory + warmup)
                resource = await asyncio.wait_for(
                    self._create_warmed_resource(),
                    timeout=self._warmup_timeout_sec + 5.0  # Extra time for factory
                )
                self._warm_queue.put_nowait(resource)
                added += 1
                logger.debug(f"[{self._name}] Warmed resource {added}/{target}")
            except asyncio.QueueFull:
                logger.debug(f"[{self._name}] Warm queue full, stopping fill")
                break
            except asyncio.TimeoutError:
                logger.error(
                    f"[{self._name}] Resource creation timed out (resource {i+1}/{target}). "
                    f"Continuing with partial pool."
                )
                # Continue trying to create remaining resources
                continue
            except Exception as e:
                logger.error(
                    f"[{self._name}] Failed to create warm resource {i+1}/{target}: {e}",
                    exc_info=True
                )
                # Continue trying to create remaining resources
                continue

        self._metrics.warm_pool_size = self._warm_queue.qsize()
        
        if added < target:
            logger.warning(
                f"[{self._name}] Partial warmup: {added}/{target} resources ready. "
                f"Pool will fall back to on-demand allocation for remaining capacity."
            )
        
        return added

    async def _cleanup_stale_sessions(self) -> int:
        """Remove stale session resources. Returns number removed."""
        removed = 0
        now = time.time()
        stale_sessions = []

        async with self._lock:
            for session_id, (_, last_used) in self._session_cache.items():
                if (now - last_used) > self._session_max_age_sec:
                    stale_sessions.append(session_id)

            for session_id in stale_sessions:
                self._session_cache.pop(session_id, None)
                removed += 1

            self._metrics.active_sessions = len(self._session_cache)

        if removed > 0:
            logger.info(f"[{self._name}] Cleaned up {removed} stale sessions")

        return removed

    async def _background_warmup_loop(self) -> None:
        """Background task that maintains warm pool level and cleans up stale sessions."""
        logger.debug(f"[{self._name}] Background warmup loop started")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self._warmup_interval_sec)

                if self._shutdown_event.is_set():
                    break

                # Refill warm pool
                added = await self._fill_warm_pool()
                if added > 0:
                    logger.debug(f"[{self._name}] Added {added} resources to warm pool")

                # Cleanup stale sessions
                await self._cleanup_stale_sessions()

                self._metrics.warmup_cycles += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self._name}] Background warmup error: {e}")

        logger.debug(f"[{self._name}] Background warmup loop stopped")

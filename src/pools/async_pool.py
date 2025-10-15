"""
Async Pool - Unified Resource Pool Manager
===================================================

Combines the simplicity of AsyncPool with the advanced features of DedicatedTtsPoolManager:

1. **Generic Resource Pooling**: Works with any factory function and resource type
2. **Session-aware Allocation**: Optional dedicated resources per session ID  
3. **Multi-tier Strategy**: Dedicated → Warm → Cold allocation tiers
4. **Background Maintenance**: Pre-warming and cleanup loops
5. **Comprehensive Metrics**: Performance tracking and monitoring
6. **Backward Compatibility**: Drop-in replacement for AsyncPool

This unified approach eliminates redundancy while providing advanced optimizations
for high-concurrency voice applications.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import (
    Awaitable,
    Callable,
    Dict,
    Generic,
    Optional,
    TypeVar,
    Any,
    Tuple,
)

from utils.ml_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class AllocationTier(Enum):
    """Resource allocation tiers for different latency requirements."""

    DEDICATED = "dedicated"  # Per-session, 0ms latency
    WARM = "warm"  # Pre-warmed pool, <50ms latency  
    COLD = "cold"  # On-demand creation, <200ms latency


@dataclass
class PoolMetrics:
    """Comprehensive pool metrics for monitoring and optimization."""

    allocations_total: int = 0
    allocations_dedicated: int = 0
    allocations_warm: int = 0
    allocations_cold: int = 0
    active_sessions: int = 0
    pool_exhaustions: int = 0
    cleanup_operations: int = 0
    background_tasks_active: int = 0
    last_updated: float = field(default_factory=time.time)


@dataclass
class SessionResource(Generic[T]):
    """Resource bound to a specific session."""

    resource: T
    session_id: str
    allocated_at: float
    last_used: float
    tier: AllocationTier
    resource_id: str

    def is_stale(self, max_age_seconds: float = 1800) -> bool:
        """Check if resource is stale and should be recycled."""
        return (time.time() - self.last_used) > max_age_seconds

    def touch(self) -> None:
        """Update last_used timestamp."""
        self.last_used = time.time()


class AsyncPool(Generic[T]):
    """
    Asynchronous resource pool with unified capabilities.
    
    Features:
    - Generic resource pooling (AsyncPool compatibility)
    - Optional session-aware allocation (DedicatedTts capabilities)
    - Multi-tier allocation strategy
    - Background maintenance tasks
    - Comprehensive metrics and monitoring
    """

    def __init__(
        self,
        factory: Callable[[], Awaitable[T]],
        size: int,
        *,
        # Session-aware features (optional)
        enable_session_awareness: bool = False,
        max_dedicated_resources: Optional[int] = None,
        # Background maintenance (optional)
        enable_prewarming: bool = False,
        prewarming_batch_size: int = 5,
        enable_cleanup: bool = False,
        cleanup_interval_seconds: float = 180,
        resource_max_age_seconds: float = 1800,
        # Pool behavior
        acquire_timeout: Optional[float] = None,
    ):
        """
        Initialize the async pool.
        
        Args:
            factory: Async factory function to create resource instances
            size: Base pool size for warm resources
            enable_session_awareness: Enable per-session dedicated resources
            max_dedicated_resources: Maximum dedicated resources (defaults to size * 2)
            enable_prewarming: Enable background pool pre-warming
            prewarming_batch_size: Batch size for pre-warming operations
            enable_cleanup: Enable background cleanup of stale resources
            cleanup_interval_seconds: Interval between cleanup operations
            resource_max_age_seconds: Maximum age before resource is considered stale
            acquire_timeout: Default timeout for resource acquisition
        """
        if not callable(factory):
            raise TypeError("Factory must be a callable function")
        if size <= 0:
            raise ValueError("Pool size must be positive")

        # Core configuration
        self._factory = factory
        self._size = size
        self._acquire_timeout = acquire_timeout

        # Session-aware configuration
        self._enable_session_awareness = enable_session_awareness
        self._max_dedicated_resources = max_dedicated_resources or (size * 2)

        # Background task configuration
        self._enable_prewarming = enable_prewarming
        self._prewarming_batch_size = prewarming_batch_size
        self._enable_cleanup = enable_cleanup
        self._cleanup_interval = cleanup_interval_seconds
        self._resource_max_age = resource_max_age_seconds

        # Core pool storage
        self._warm_pool: asyncio.Queue[T] = asyncio.Queue(maxsize=size)
        
        # Session-aware storage (only used if enabled)
        self._dedicated_resources: Dict[str, SessionResource[T]] = {}

        # Thread safety
        self._allocation_lock = asyncio.Lock()
        self._cleanup_lock = asyncio.Lock()

        # State management
        self._ready_event = asyncio.Event()
        self._is_initialized = False
        self._is_shutting_down = False

        # Background tasks
        self._prewarming_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Metrics
        self._metrics = PoolMetrics()

        logger.debug(
            f"Initialized AsyncPool: size={size}, "
            f"session_aware={enable_session_awareness}, "
            f"prewarming={enable_prewarming}, cleanup={enable_cleanup}"
        )

    async def prepare(self) -> None:
        """Initialize the pool and start background tasks."""
        if self._ready_event.is_set():
            logger.debug("Pool already prepared")
            return

        try:
            logger.debug(f"Preparing pool with {self._size} resources")

            # Pre-populate warm pool
            for i in range(self._size):
                logger.debug(f"Creating resource {i+1}/{self._size}")
                resource = await self._factory()
                await self._warm_pool.put(resource)

            # Start background tasks if enabled
            if self._enable_prewarming:
                self._prewarming_task = asyncio.create_task(self._prewarming_loop())
                self._metrics.background_tasks_active += 1

            if self._enable_cleanup and self._enable_session_awareness:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                self._metrics.background_tasks_active += 1

            self._ready_event.set()
            self._is_initialized = True
            self._metrics.last_updated = time.time()

            logger.info(
                f"pool prepared: warm={self._warm_pool.qsize()}/{self._size}, "
                f"background_tasks={self._metrics.background_tasks_active}"
            )

        except Exception as e:
            logger.error(f"Failed to prepare pool: {e}")
            raise

    # =========================================================================
    # LEGACY ASYNCPOOL COMPATIBILITY
    # =========================================================================

    async def acquire(self, timeout: Optional[float] = None) -> T:
        """
        Acquire a resource from the pool (AsyncPool compatibility).
        
        This method provides backward compatibility with the original AsyncPool.
        For session-aware allocation, use acquire_for_session() instead.
        """
        if not self._ready_event.is_set():
            raise RuntimeError("Pool must be prepared before acquiring resources")

        timeout = timeout or self._acquire_timeout

        try:
            if timeout is None:
                return await self._warm_pool.get()
            else:
                return await asyncio.wait_for(self._warm_pool.get(), timeout=timeout)
        except asyncio.TimeoutError as e:
            self._metrics.pool_exhaustions += 1
            raise TimeoutError("Pool acquire timeout") from e

    async def release(self, resource: T) -> None:
        """
        Return a resource to the pool (AsyncPool compatibility).
        """
        if resource is None:
            raise ValueError("Cannot release None resource to pool")

        try:
            await self._warm_pool.put(resource)
        except Exception as e:
            logger.error(f"Failed to release resource to pool: {e}")
            raise

    @asynccontextmanager
    async def lease(self, timeout: Optional[float] = None):
        """
        Context manager for automatic resource acquisition and release.
        (AsyncPool compatibility)
        """
        resource = await self.acquire(timeout=timeout)
        try:
            yield resource
        finally:
            await self.release(resource)

    # =========================================================================
    # SESSION-AWARE ALLOCATION 
    # =========================================================================

    async def acquire_for_session(
        self, session_id: str, timeout: Optional[float] = None
    ) -> Tuple[T, AllocationTier]:
        """
        Acquire a resource for a specific session with tier tracking.
        
        Priority:
        1. Return existing dedicated resource (0ms latency)
        2. Allocate new dedicated resource from warm pool (<50ms)
        3. Create on-demand resource as fallback (<200ms)
        
        Returns:
            Tuple of (resource, allocation tier)
        """
        if not self._enable_session_awareness:
            # Fallback to standard allocation
            resource = await self.acquire(timeout)
            self._metrics.allocations_warm += 1
            return resource, AllocationTier.WARM

        async with self._allocation_lock:
            start_time = time.time()

            # Check for existing dedicated resource
            if session_id in self._dedicated_resources:
                session_resource = self._dedicated_resources[session_id]
                session_resource.touch()

                allocation_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"[PERF] Retrieved existing dedicated resource for session {session_id} "
                    f"in {allocation_time:.1f}ms"
                )

                self._metrics.allocations_dedicated += 1
                return session_resource.resource, AllocationTier.DEDICATED

            # Try to allocate from warm pool
            warm_resource = await self._try_acquire_warm_resource()
            if warm_resource:
                session_resource = SessionResource(
                    resource=warm_resource,
                    session_id=session_id,
                    allocated_at=time.time(),
                    last_used=time.time(),
                    tier=AllocationTier.WARM,
                    resource_id=str(uuid.uuid4())[:8],
                )

                self._dedicated_resources[session_id] = session_resource

                allocation_time = (time.time() - start_time) * 1000
                logger.info(
                    f"[PERF] Allocated warm resource for session {session_id} "
                    f"in {allocation_time:.1f}ms (resource_id={session_resource.resource_id})"
                )

                self._metrics.allocations_warm += 1
                self._metrics.active_sessions = len(self._dedicated_resources)
                return warm_resource, AllocationTier.WARM

            # Fallback: Create on-demand resource
            if len(self._dedicated_resources) < self._max_dedicated_resources:
                cold_resource = await self._factory()
                session_resource = SessionResource(
                    resource=cold_resource,
                    session_id=session_id,
                    allocated_at=time.time(), 
                    last_used=time.time(),
                    tier=AllocationTier.COLD,
                    resource_id=str(uuid.uuid4())[:8],
                )

                self._dedicated_resources[session_id] = session_resource

                allocation_time = (time.time() - start_time) * 1000
                logger.warning(
                    f"[PERF] Created cold resource for session {session_id} "
                    f"in {allocation_time:.1f}ms (resource_id={session_resource.resource_id})"
                )

                self._metrics.allocations_cold += 1
                self._metrics.active_sessions = len(self._dedicated_resources)
                return cold_resource, AllocationTier.COLD

            # Pool exhaustion
            self._metrics.pool_exhaustions += 1
            allocation_time = (time.time() - start_time) * 1000
            logger.error(
                f"🚨 Pool exhausted! Cannot allocate resource for session {session_id} "
                f"(attempted in {allocation_time:.1f}ms, active_sessions={len(self._dedicated_resources)})"
            )

            raise RuntimeError(
                f"Pool exhausted, cannot allocate resource for session {session_id}"
            )

    def snapshot(self) -> Dict[str, Any]:
        """Return a lightweight status dump for diagnostics."""
        status: Dict[str, Any] = {
            "initialized": self._is_initialized,
            "shutting_down": self._is_shutting_down,
            "warm_available": self._warm_pool.qsize(),
            "warm_capacity": self._warm_pool.maxsize,
            "pending_waiters": len(getattr(self._warm_pool, "_getters", [])),
            "session_aware": self._enable_session_awareness,
        }

        if self._enable_session_awareness:
            status["dedicated_active"] = len(self._dedicated_resources)
            status["dedicated_capacity"] = self._max_dedicated_resources

        status["metrics"] = asdict(self._metrics)
        return status

    @property
    def session_awareness_enabled(self) -> bool:
        """Expose whether the pool tracks per-session resources."""
        return self._enable_session_awareness

    async def release_session_resource(self, session_id: str) -> bool:
        """
        Release a session's dedicated resource back to the warm pool.
        
        Returns:
            True if resource was released, False if not found
        """
        if not self._enable_session_awareness:
            logger.debug("Session awareness disabled, no action taken")
            return False

        async with self._allocation_lock:
            session_resource = self._dedicated_resources.pop(session_id, None)
            if not session_resource:
                logger.debug(f"No dedicated resource found for session {session_id}")
                return False

            # Try to return resource to warm pool if not full
            try:
                self._warm_pool.put_nowait(session_resource.resource)
                logger.info(
                    f"[PERF] Released resource from session {session_id} back to warm pool "
                    f"(resource_id={session_resource.resource_id}, tier={session_resource.tier.value})"
                )
            except asyncio.QueueFull:
                # Warm pool is full, dispose of the resource
                logger.debug(
                    f"Warm pool full, disposing resource from session {session_id} "
                    f"(resource_id={session_resource.resource_id})"
                )

            self._metrics.active_sessions = len(self._dedicated_resources)
            self._metrics.cleanup_operations += 1
            return True

    async def release_for_session(
        self, session_id: Optional[str], resource: Optional[T] = None
    ) -> bool:
        """Release a resource regardless of session awareness configuration."""
        if self._enable_session_awareness:
            if not session_id:
                logger.debug("release_for_session called without session_id")
                return False
            return await self.release_session_resource(session_id)

        if resource is None:
            logger.warning("release_for_session requires resource when session awareness is disabled")
            return False

        await self.release(resource)
        self._metrics.cleanup_operations += 1
        return True

    @asynccontextmanager
    async def lease_for_session(
        self, session_id: str, timeout: Optional[float] = None
    ):
        """
        Context manager for session-aware resource acquisition and release.
        """
        resource, tier = await self.acquire_for_session(session_id, timeout)
        try:
            yield resource, tier
        finally:
            if tier == AllocationTier.DEDICATED:
                # Dedicated resources stay bound to session
                pass
            else:
                # Return non-dedicated resources to pool
                await self.release(resource)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _try_acquire_warm_resource(self) -> Optional[T]:
        """Try to get a resource from the warm pool without blocking."""
        try:
            return self._warm_pool.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _prewarming_loop(self) -> None:
        """Background task to maintain warm pool levels."""
        while not self._is_shutting_down:
            try:
                current_size = self._warm_pool.qsize()
                target_size = self._size
                deficit = target_size - current_size

                if deficit > 0:
                    logger.debug(
                        f"Replenishing warm pool: {current_size}/{target_size} (+{deficit})"
                    )

                    # Create resources in small batches
                    for i in range(0, deficit, self._prewarming_batch_size):
                        batch_size = min(self._prewarming_batch_size, deficit - i)
                        batch_tasks = [
                            self._create_and_add_warm_resource(f"replenish-{i + j}")
                            for j in range(batch_size)
                        ]
                        await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Sleep before next check
                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                logger.debug("Pre-warming loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pre-warming loop: {e}")
                await asyncio.sleep(60)  # Back off on errors

    async def _create_and_add_warm_resource(self, batch_id: str) -> None:
        """Create a resource and add it to the warm pool."""
        try:
            resource = await self._factory()
            await self._warm_pool.put(resource)
            logger.debug(f"Pre-warmed resource added (batch={batch_id})")
        except Exception as e:
            logger.error(f"Failed to pre-warm resource (batch={batch_id}): {e}")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale session resources."""
        while not self._is_shutting_down:
            try:
                async with self._cleanup_lock:
                    await self._cleanup_stale_resources()

                await asyncio.sleep(self._cleanup_interval)

            except asyncio.CancelledError:
                logger.debug("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_stale_resources(self) -> None:
        """Remove stale dedicated resources and return them to warm pool."""
        stale_sessions = []

        for session_id, session_resource in self._dedicated_resources.items():
            if session_resource.is_stale(self._resource_max_age):
                stale_sessions.append(session_id)

        if stale_sessions:
            logger.info(f"🧹 Cleaning up {len(stale_sessions)} stale resources")

            for session_id in stale_sessions:
                await self.release_session_resource(session_id)

    # =========================================================================
    # MONITORING AND METRICS
    # =========================================================================

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive pool metrics."""
        self._metrics.allocations_total = (
            self._metrics.allocations_dedicated
            + self._metrics.allocations_warm
            + self._metrics.allocations_cold
        )
        self._metrics.last_updated = time.time()

        return {
            "allocations": {
                "total": self._metrics.allocations_total,
                "dedicated": self._metrics.allocations_dedicated,
                "warm": self._metrics.allocations_warm,
                "cold": self._metrics.allocations_cold,
            },
            "pool_status": {
                "active_sessions": self._metrics.active_sessions,
                "warm_pool_size": self._warm_pool.qsize(),
                "warm_pool_capacity": self._size,
                "max_dedicated_resources": self._max_dedicated_resources,
            },
            "features": {
                "session_awareness_enabled": self._enable_session_awareness,
                "prewarming_enabled": self._enable_prewarming,
                "cleanup_enabled": self._enable_cleanup,
                "background_tasks_active": self._metrics.background_tasks_active,
            },
            "performance": {
                "pool_exhaustions": self._metrics.pool_exhaustions,
                "cleanup_operations": self._metrics.cleanup_operations,
            },
            "health": {
                "is_initialized": self._is_initialized,
                "is_shutting_down": self._is_shutting_down,
                "last_updated": self._metrics.last_updated,
            },
        }

    # =========================================================================
    # LIFECYCLE MANAGEMENT
    # =========================================================================

    async def shutdown(self) -> None:
        """Gracefully shutdown the pool."""
        if self._is_shutting_down:
            return

        logger.info("🛑 Shutting down Async Pool...")
        self._is_shutting_down = True

        # Cancel background tasks
        tasks_to_cancel = []
        if self._prewarming_task:
            tasks_to_cancel.append(self._prewarming_task)
        if self._cleanup_task:
            tasks_to_cancel.append(self._cleanup_task)

        for task in tasks_to_cancel:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Clean up all resources
        async with self._allocation_lock:
            self._dedicated_resources.clear()

            # Clear warm pool
            while not self._warm_pool.empty():
                try:
                    self._warm_pool.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info("✅ Async Pool shutdown complete")

    # Legacy property for backward compatibility
    @property
    def _q(self) -> asyncio.Queue[T]:
        """Backward compatibility with AsyncPool._q access."""
        return self._warm_pool

    @property
    def _ready(self) -> asyncio.Event:
        """Backward compatibility with AsyncPool._ready access."""
        return self._ready_event
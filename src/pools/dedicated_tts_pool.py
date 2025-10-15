"""
Enhanced TTS Pool Manager with Dedicated Per-Session Clients & Pre-Warming
==========================================================================

 Eliminate TTS pool contention through:
1. Dedicated TTS clients per session (0ms latency)
2. Pre-warmed client inventory (instant allocation)
3. Intelligent fallback tiers for scale
4. 🧹 Automatic cleanup and lifecycle management

This replaces the shared AsyncPool approach with a session-aware
multi-tier architecture designed for 1000+ concurrent sessions.
"""

import asyncio
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any, Tuple
from enum import Enum

from src.speech.text_to_speech import SpeechSynthesizer
from src.common.ml_logging import get_logger

logger = get_logger("dedicated_tts_pool")

# Environment-based configuration for production optimization
TTS_POOL_SIZE = int(os.getenv("POOL_SIZE_TTS", "100"))
TTS_POOL_PREWARMING_ENABLED = (
    os.getenv("TTS_POOL_PREWARMING_ENABLED", "true").lower() == "true"
)
TTS_PREWARMING_BATCH_SIZE = int(os.getenv("POOL_PREWARMING_BATCH_SIZE", "10"))
TTS_CLIENT_MAX_AGE_SECONDS = int(os.getenv("CLIENT_MAX_AGE_SECONDS", "3600"))
TTS_CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "180"))


class ClientTier(Enum):
    """TTS client allocation tiers for different latency requirements."""

    DEDICATED = "dedicated"  # Per-session, 0ms latency
    WARM = "warm"  # Pre-warmed pool, <50ms latency
    COLD = "cold"  # On-demand creation, <200ms latency


@dataclass
class TtsClientMetrics:
    """Metrics for TTS client usage and performance."""

    allocations_total: int = 0
    allocations_dedicated: int = 0
    allocations_warm: int = 0
    allocations_cold: int = 0
    active_sessions: int = 0
    pool_exhaustions: int = 0
    cleanup_operations: int = 0
    last_updated: float = 0.0


@dataclass
class TtsSessionClient:
    """Dedicated TTS client bound to a specific session."""

    client: SpeechSynthesizer
    session_id: str
    allocated_at: float
    last_used: float
    tier: ClientTier
    client_id: str

    def is_stale(self, max_age_seconds: float = 1800) -> bool:
        """Check if client is stale and should be recycled."""
        return (time.time() - self.last_used) > max_age_seconds

    def touch(self) -> None:
        """Update last_used timestamp."""
        self.last_used = time.time()


class DedicatedTtsPoolManager:
    """
    Enhanced TTS pool manager with dedicated per-session clients.

    Architecture:
    - Tier 1: Dedicated clients per active session (0ms latency)
    - Tier 2: Pre-warmed client pool (fast allocation)
    - Tier 3: On-demand fallback (graceful degradation)

    Features:
    - Zero pool contention for active sessions
    - Automatic client pre-warming and lifecycle management
    - Comprehensive metrics and monitoring
    - Thread-safe operations with asyncio locks
    """

    def __init__(
        self,
        *,
        warm_pool_size: int = None,
        max_dedicated_clients: int = None,
        prewarming_batch_size: int = None,
        cleanup_interval_seconds: float = None,
        client_max_age_seconds: float = None,
        enable_prewarming: bool = None,
    ):
        # Use environment variables with defaults for production optimization
        self._warm_pool_size = warm_pool_size or TTS_POOL_SIZE
        self._max_dedicated_clients = max_dedicated_clients or (TTS_POOL_SIZE * 2)
        self._prewarming_batch_size = prewarming_batch_size or TTS_PREWARMING_BATCH_SIZE
        self._cleanup_interval = (
            cleanup_interval_seconds or TTS_CLEANUP_INTERVAL_SECONDS
        )
        self._client_max_age = client_max_age_seconds or TTS_CLIENT_MAX_AGE_SECONDS
        self._enable_prewarming = (
            enable_prewarming
            if enable_prewarming is not None
            else TTS_POOL_PREWARMING_ENABLED
        )

        # Session-specific dedicated clients
        self._dedicated_clients: Dict[str, TtsSessionClient] = {}

        # Pre-warmed client pool
        self._warm_pool: asyncio.Queue = asyncio.Queue(maxsize=warm_pool_size)

        # Thread safety
        self._allocation_lock = asyncio.Lock()
        self._cleanup_lock = asyncio.Lock()

        # Metrics and monitoring
        self._metrics = TtsClientMetrics()

        # Background tasks
        self._prewarming_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # State management
        self._is_initialized = False
        self._is_shutting_down = False

    async def initialize(self) -> None:
        """Initialize the pool manager and start background tasks."""
        if self._is_initialized:
            return

        logger.info("Initializing Enhanced TTS Pool Manager")

        # Pre-warm the pool if enabled
        if self._enable_prewarming:
            await self._prewarm_pool_initial()

        # Start background tasks
        self._prewarming_task = asyncio.create_task(self._prewarming_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        self._is_initialized = True
        self._metrics.last_updated = time.time()

        logger.info(
            f"✅ Enhanced TTS Pool Manager initialized - "
            f"warm_pool_size={self._warm_pool_size}, "
            f"max_dedicated={self._max_dedicated_clients}"
        )

    async def get_dedicated_client(
        self, session_id: str
    ) -> Tuple[SpeechSynthesizer, ClientTier]:
        """
        Get a dedicated TTS client for a session with tier tracking.

        Priority:
        1. Return existing dedicated client (0ms latency)
        2. Allocate new dedicated client from warm pool (<50ms)
        3. Create on-demand client as fallback (<200ms)

        Returns:
            Tuple of (TTS client, allocation tier)
        """
        async with self._allocation_lock:
            start_time = time.time()

            # Check for existing dedicated client
            if session_id in self._dedicated_clients:
                session_client = self._dedicated_clients[session_id]
                session_client.touch()

                allocation_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"[PERF] Retrieved existing dedicated TTS client for session {session_id} "
                    f"in {allocation_time:.1f}ms"
                )

                self._metrics.allocations_dedicated += 1
                return session_client.client, ClientTier.DEDICATED

            # Try to allocate from warm pool
            warm_client = await self._try_allocate_warm_client()
            if warm_client:
                session_client = TtsSessionClient(
                    client=warm_client,
                    session_id=session_id,
                    allocated_at=time.time(),
                    last_used=time.time(),
                    tier=ClientTier.WARM,
                    client_id=str(uuid.uuid4())[:8],
                )

                self._dedicated_clients[session_id] = session_client

                allocation_time = (time.time() - start_time) * 1000
                logger.info(
                    f"[PERF] Allocated warm TTS client for session {session_id} "
                    f"in {allocation_time:.1f}ms (client_id={session_client.client_id})"
                )

                self._metrics.allocations_warm += 1
                self._metrics.active_sessions = len(self._dedicated_clients)
                return warm_client, ClientTier.WARM

            # Fallback: Create on-demand client
            if len(self._dedicated_clients) < self._max_dedicated_clients:
                cold_client = await self._create_client()
                session_client = TtsSessionClient(
                    client=cold_client,
                    session_id=session_id,
                    allocated_at=time.time(),
                    last_used=time.time(),
                    tier=ClientTier.COLD,
                    client_id=str(uuid.uuid4())[:8],
                )

                self._dedicated_clients[session_id] = session_client

                allocation_time = (time.time() - start_time) * 1000
                logger.warning(
                    f"[PERF] Created cold TTS client for session {session_id} "
                    f"in {allocation_time:.1f}ms (client_id={session_client.client_id})"
                )

                self._metrics.allocations_cold += 1
                self._metrics.active_sessions = len(self._dedicated_clients)
                return cold_client, ClientTier.COLD

            # Pool exhaustion - return None for graceful degradation
            self._metrics.pool_exhaustions += 1
            allocation_time = (time.time() - start_time) * 1000
            logger.error(
                f"🚨 TTS pool exhausted! Cannot allocate client for session {session_id} "
                f"(attempted in {allocation_time:.1f}ms, active_sessions={len(self._dedicated_clients)})"
            )

            raise RuntimeError(
                f"TTS pool exhausted, cannot allocate client for session {session_id}"
            )

    async def release_session_client(self, session_id: str) -> bool:
        """
        Release a dedicated client back to the warm pool.

        Returns:
            True if client was released, False if not found
        """
        async with self._allocation_lock:
            session_client = self._dedicated_clients.pop(session_id, None)
            if not session_client:
                logger.debug(f"No dedicated TTS client found for session {session_id}")
                return False

            # Try to return client to warm pool if not full
            try:
                self._warm_pool.put_nowait(session_client.client)
                logger.info(
                    f"[PERF] Released TTS client from session {session_id} back to warm pool "
                    f"(client_id={session_client.client_id}, tier={session_client.tier.value})"
                )
            except asyncio.QueueFull:
                # Warm pool is full, dispose of the client
                logger.debug(
                    f"Warm pool full, disposing TTS client from session {session_id} "
                    f"(client_id={session_client.client_id})"
                )

            self._metrics.active_sessions = len(self._dedicated_clients)
            self._metrics.cleanup_operations += 1
            return True

    async def _try_allocate_warm_client(self) -> Optional[SpeechSynthesizer]:
        """Try to get a client from the warm pool without blocking."""
        try:
            return self._warm_pool.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _create_client(self) -> SpeechSynthesizer:
        """Create a new TTS client instance."""
        return SpeechSynthesizer()

    async def _prewarm_pool_initial(self) -> None:
        """Pre-warm the pool with initial clients."""
        logger.info(f"Pre-warming TTS pool with {self._warm_pool_size} clients...")

        tasks = []
        for i in range(self._warm_pool_size):
            task = asyncio.create_task(self._create_and_add_warm_client(f"init-{i}"))
            tasks.append(task)

        # Create clients in batches to avoid overwhelming the Speech service
        for i in range(0, len(tasks), self._prewarming_batch_size):
            batch = tasks[i : i + self._prewarming_batch_size]
            await asyncio.gather(*batch, return_exceptions=True)

            # Small delay between batches
            if i + self._prewarming_batch_size < len(tasks):
                await asyncio.sleep(0.1)

        warm_count = self._warm_pool.qsize()
        logger.info(
            f"✅ Pre-warming complete: {warm_count}/{self._warm_pool_size} clients ready"
        )

    async def _create_and_add_warm_client(self, batch_id: str) -> None:
        """Create a client and add it to the warm pool."""
        try:
            client = await self._create_client()
            await self._warm_pool.put(client)
            logger.debug(f"Pre-warmed TTS client added (batch={batch_id})")
        except Exception as e:
            logger.error(f"Failed to pre-warm TTS client (batch={batch_id}): {e}")

    async def _prewarming_loop(self) -> None:
        """Background task to maintain warm pool levels."""
        while not self._is_shutting_down:
            try:
                current_size = self._warm_pool.qsize()
                target_size = self._warm_pool_size
                deficit = target_size - current_size

                if deficit > 0:
                    logger.debug(
                        f"Replenishing warm pool: {current_size}/{target_size} (+{deficit})"
                    )

                    # Create clients in small batches
                    for i in range(0, deficit, self._prewarming_batch_size):
                        batch_size = min(self._prewarming_batch_size, deficit - i)
                        batch_tasks = [
                            self._create_and_add_warm_client(f"replenish-{i + j}")
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

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale clients."""
        while not self._is_shutting_down:
            try:
                async with self._cleanup_lock:
                    await self._cleanup_stale_clients()

                await asyncio.sleep(self._cleanup_interval)

            except asyncio.CancelledError:
                logger.debug("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_stale_clients(self) -> None:
        """Remove stale dedicated clients and return them to warm pool."""
        stale_sessions = []

        for session_id, session_client in self._dedicated_clients.items():
            if session_client.is_stale(self._client_max_age):
                stale_sessions.append(session_id)

        if stale_sessions:
            logger.info(f"🧹 Cleaning up {len(stale_sessions)} stale TTS clients")

            for session_id in stale_sessions:
                await self.release_session_client(session_id)

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
                "warm_pool_capacity": self._warm_pool_size,
                "max_dedicated_clients": self._max_dedicated_clients,
            },
            "performance": {
                "pool_exhaustions": self._metrics.pool_exhaustions,
                "cleanup_operations": self._metrics.cleanup_operations,
                "prewarming_enabled": self._enable_prewarming,
            },
            "health": {
                "is_initialized": self._is_initialized,
                "is_shutting_down": self._is_shutting_down,
                "last_updated": self._metrics.last_updated,
            },
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown the pool manager."""
        if self._is_shutting_down:
            return

        logger.info("🛑 Shutting down Enhanced TTS Pool Manager...")
        self._is_shutting_down = True

        # Cancel background tasks
        if self._prewarming_task:
            self._prewarming_task.cancel()
            try:
                await self._prewarming_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clean up all clients
        async with self._allocation_lock:
            self._dedicated_clients.clear()

            # Clear warm pool
            while not self._warm_pool.empty():
                try:
                    self._warm_pool.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info("✅ Enhanced TTS Pool Manager shutdown complete")


# Global instance for application use
_global_dedicated_tts_manager: Optional[DedicatedTtsPoolManager] = None


async def get_dedicated_tts_manager() -> DedicatedTtsPoolManager:
    """Get the global dedicated TTS manager instance."""
    global _global_dedicated_tts_manager

    if _global_dedicated_tts_manager is None:
        _global_dedicated_tts_manager = DedicatedTtsPoolManager()
        await _global_dedicated_tts_manager.initialize()

    return _global_dedicated_tts_manager


async def cleanup_dedicated_tts_manager() -> None:
    """Clean up the global dedicated TTS manager."""
    global _global_dedicated_tts_manager

    if _global_dedicated_tts_manager:
        await _global_dedicated_tts_manager.shutdown()
        _global_dedicated_tts_manager = None

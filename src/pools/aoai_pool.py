"""
Azure OpenAI Client Pool for High-Concurrency Voice Applications
================================================================

This module provides a dedicated client pool for Azure OpenAI to eliminate 
resource contention and optimize throughput for concurrent voice sessions.

Key Features:
- Multiple client instances to avoid connection pooling bottlenecks
- Session-dedicated client allocation for optimal performance
- Automatic failover and client health monitoring
- Rate limit aware request distribution
"""

import asyncio
import time
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
import threading

from apps.rtagent.backend.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)

# Configuration
AOAI_POOL_ENABLED = os.getenv("AOAI_POOL_ENABLED", "true").lower() == "true"
AOAI_POOL_SIZE = int(os.getenv("AOAI_POOL_SIZE", "10"))


@dataclass
class ClientMetrics:
    """Tracks performance metrics for an Azure OpenAI client."""

    requests_count: int = 0
    avg_response_time: float = 0.0
    last_request_time: float = 0.0
    error_count: int = 0
    consecutive_errors: int = 0

    def update_success(self, response_time: float):
        """Update metrics after successful request."""
        self.requests_count += 1
        self.avg_response_time = (
            self.avg_response_time * (self.requests_count - 1) + response_time
        ) / self.requests_count
        self.last_request_time = time.time()
        self.consecutive_errors = 0

    def update_error(self):
        """Update metrics after failed request."""
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_request_time = time.time()


class AOAIClientPool:
    """
    High-performance Azure OpenAI client pool for concurrent voice sessions.

    Manages multiple client instances to eliminate connection bottlenecks and
    provides session-dedicated allocation for optimal throughput.
    """

    def __init__(self, pool_size: int = None):
        """
        Initialize the Azure OpenAI client pool.

        Args:
            pool_size: Number of client instances to maintain in the pool.
                      Defaults to AOAI_POOL_SIZE environment variable (10).
        """
        self.pool_size = pool_size or AOAI_POOL_SIZE
        self.clients: List[AzureOpenAI] = []
        self.client_metrics: List[ClientMetrics] = []
        self.session_allocations: Dict[str, int] = {}  # session_id -> client_index
        self.lock = threading.RLock()
        self._initialized = False

        logger.info(
            f"AOAI client pool initializing with {self.pool_size} clients (enabled={AOAI_POOL_ENABLED})"
        )

    async def initialize(self) -> None:
        """Initialize the client pool with multiple Azure OpenAI clients."""
        if self._initialized:
            return

        try:
            for i in range(self.pool_size):
                client = self._create_client()
                self.clients.append(client)
                self.client_metrics.append(ClientMetrics())
                logger.debug(f"AOAI client {i+1}/{self.pool_size} initialized")

            self._initialized = True
            logger.debug(
                f"AOAI client pool initialized successfully with {len(self.clients)} clients"
            )

        except Exception as e:
            logger.error(f"AOAI client pool initialization failed: {e}")
            raise

    def _create_client(self) -> AzureOpenAI:
        """Create a single Azure OpenAI client instance."""
        if AZURE_OPENAI_KEY:
            return AzureOpenAI(
                api_version="2025-01-01-preview",
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_KEY,
                max_retries=1,  # Lower retries for faster failover
                timeout=30.0,  # Shorter timeout for responsiveness
            )
        else:
            # Use managed identity
            credential = DefaultAzureCredential()
            azure_ad_token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            return AzureOpenAI(
                api_version="2025-01-01-preview",
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                azure_ad_token_provider=azure_ad_token_provider,
                max_retries=1,
                timeout=30.0,
            )

    async def get_dedicated_client(self, session_id: str) -> AzureOpenAI:
        """
        Get a dedicated client for a session with automatic allocation.

        Args:
            session_id: Unique session identifier

        Returns:
            Dedicated AzureOpenAI client for the session
        """
        if not self._initialized:
            await self.initialize()

        with self.lock:
            # Check if session already has a dedicated client
            if session_id in self.session_allocations:
                client_index = self.session_allocations[session_id]
                logger.debug(
                    f"Session {session_id} using existing AOAI client {client_index}"
                )
                return self.clients[client_index]

            # Allocate new client using least-loaded strategy
            client_index = self._find_best_client()
            self.session_allocations[session_id] = client_index

            logger.info(f"AOAI client {client_index} allocated to session {session_id}")
            return self.clients[client_index]

    def _find_best_client(self) -> int:
        """Find the best available client using performance metrics."""
        best_index = 0
        best_score = float("inf")

        for i, metrics in enumerate(self.client_metrics):
            # Skip clients with consecutive errors
            if metrics.consecutive_errors >= 3:
                continue

            # Calculate load score (lower is better)
            active_sessions = sum(
                1 for idx in self.session_allocations.values() if idx == i
            )
            load_score = active_sessions + (
                metrics.avg_response_time / 1000
            )  # Convert ms to seconds

            if load_score < best_score:
                best_score = load_score
                best_index = i

        return best_index

    async def release_client(self, session_id: str) -> None:
        """
        Release the dedicated client for a session.

        Args:
            session_id: Session identifier to release
        """
        with self.lock:
            if session_id in self.session_allocations:
                client_index = self.session_allocations.pop(session_id)
                logger.info(
                    f"AOAI client {client_index} released from session {session_id}"
                )

    @asynccontextmanager
    async def request_context(self, session_id: str):
        """
        Context manager for tracking request performance.

        Args:
            session_id: Session making the request

        Yields:
            Tuple of (client, client_index) for the request
        """
        client = await self.get_dedicated_client(session_id)
        client_index = self.session_allocations[session_id]
        start_time = time.time()

        try:
            yield client, client_index
            # Success - update metrics
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            self.client_metrics[client_index].update_success(response_time)

        except Exception as e:
            # Error - update metrics and re-raise
            self.client_metrics[client_index].update_error()
            logger.error(
                f"AOAI request failed for session {session_id} on client {client_index}: {e}"
            )
            raise

    def get_pool_stats(self) -> Dict:
        """Get comprehensive pool statistics."""
        with self.lock:
            stats = {
                "pool_size": len(self.clients),
                "active_sessions": len(self.session_allocations),
                "clients": [],
            }

            for i, metrics in enumerate(self.client_metrics):
                active_sessions = sum(
                    1 for idx in self.session_allocations.values() if idx == i
                )
                client_stats = {
                    "client_index": i,
                    "active_sessions": active_sessions,
                    "total_requests": metrics.requests_count,
                    "avg_response_time_ms": round(metrics.avg_response_time, 2),
                    "error_count": metrics.error_count,
                    "consecutive_errors": metrics.consecutive_errors,
                    "healthy": metrics.consecutive_errors < 3,
                }
                stats["clients"].append(client_stats)

            return stats


# Global pool instance
_aoai_pool: Optional[AOAIClientPool] = None


async def get_aoai_pool() -> Optional[AOAIClientPool]:
    """Get the global Azure OpenAI client pool instance if enabled."""
    global _aoai_pool
    if not AOAI_POOL_ENABLED:
        return None
    if _aoai_pool is None:
        _aoai_pool = AOAIClientPool()
        await _aoai_pool.initialize()
    return _aoai_pool


async def get_session_client(session_id: str) -> AzureOpenAI:
    """
    Get a dedicated Azure OpenAI client for a session.

    Args:
        session_id: Unique session identifier

    Returns:
        Dedicated AzureOpenAI client optimized for the session, or None if pooling disabled
    """
    if not AOAI_POOL_ENABLED:
        logger.debug(f"AOAI pool disabled, session {session_id} will use shared client")
        return None

    pool = await get_aoai_pool()
    if pool is None:
        return None
    return await pool.get_dedicated_client(session_id)


async def release_session_client(session_id: str) -> None:
    """
    Release the dedicated client for a session.

    Args:
        session_id: Session identifier to release
    """
    if not AOAI_POOL_ENABLED or _aoai_pool is None:
        return
    await _aoai_pool.release_client(session_id)

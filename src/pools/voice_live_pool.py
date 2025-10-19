"""
Voice Live Agent Warm Pool
==========================

Pre-warms and serves connected Azure Live Voice Agent instances so handlers
can start streaming immediately with near-zero connect latency.

Design goals:
- Simple, reliable, and maintainable
- Non-blocking fast-path allocation from a warm queue
- Safe default: single-use agents (closed on release) with background refill
  to avoid cross-session state contamination
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from src.tools.ml_logging import get_logger
from apps.rtagent.backend.src.agents.Lvagent.base import AzureLiveVoiceAgent
from apps.rtagent.backend.src.agents.Lvagent.factory import build_lva_from_yaml


logger = get_logger("voice_live_pool")


# Environment configuration
VOICE_LIVE_POOL_SIZE = int(os.getenv("POOL_SIZE_VOICE_LIVE", "8"))
VOICE_LIVE_POOL_PREWARMING_ENABLED = (
    os.getenv("VOICE_LIVE_POOL_PREWARMING_ENABLED", "true").lower() == "true"
)
VOICE_LIVE_PREWARMING_BATCH_SIZE = int(os.getenv("VOICE_LIVE_PREWARMING_BATCH_SIZE", "4"))
VOICE_LIVE_AGENT_YAML = os.getenv(
    "VOICE_LIVE_AGENT_YAML",
    "apps/rtagent/backend/src/agents/Lvagent/agent_store/auth_agent.yaml",
)


@dataclass
class VoiceAgentLease:
    agent: AzureLiveVoiceAgent
    lease_id: str
    allocated_at: float


class VoiceLiveAgentPool:
    """
    Warm pool of pre-connected Azure Live Voice agents.

    Allocation strategy:
    1) Try warm queue (immediate)
    2) Fall back to on-demand connect (cold)

    Release strategy (safe default):
    - Close the agent to avoid cross-session state, then refill warm pool in background
    """

    def __init__(
        self,
        *,
        warm_pool_size: int | None = None,
        agent_yaml: str | None = None,
        enable_prewarming: bool | None = None,
        prewarming_batch_size: int | None = None,
    ) -> None:
        self._warm_pool_size = warm_pool_size or VOICE_LIVE_POOL_SIZE
        self._agent_yaml = agent_yaml or VOICE_LIVE_AGENT_YAML
        self._enable_prewarming = (
            VOICE_LIVE_POOL_PREWARMING_ENABLED
            if enable_prewarming is None
            else enable_prewarming
        )
        self._prewarming_batch_size = (
            prewarming_batch_size or VOICE_LIVE_PREWARMING_BATCH_SIZE
        )

        self._warm_pool: asyncio.Queue[AzureLiveVoiceAgent] = asyncio.Queue(
            maxsize=self._warm_pool_size
        )

        self._allocation_lock = asyncio.Lock()
        self._is_initialized = False
        self._is_shutting_down = False

        self._prewarming_task: Optional[asyncio.Task] = None
        self._metrics: Dict[str, Any] = {
            "allocations": {"warm": 0, "cold": 0},
            "pool": {"capacity": self._warm_pool_size},
            "last_updated": 0.0,
        }

    async def initialize(self, *, background_prewarm: bool = False) -> None:
        if self._is_initialized:
            return

        logger.info(
            f"Initializing Voice Live pool | size={self._warm_pool_size}, prewarm={self._enable_prewarming}"
        )

        if self._enable_prewarming:
            if background_prewarm:
                # Don't block startup; run the initial prewarm asynchronously
                asyncio.create_task(self._prewarm_initial())
            else:
                await self._prewarm_initial()

        self._prewarming_task = asyncio.create_task(self._prewarming_loop())
        self._is_initialized = True
        self._metrics["last_updated"] = time.time()
        logger.info("✅ Voice Live pool initialized")

    async def get_agent(self) -> Tuple[AzureLiveVoiceAgent, str]:
        """Get a connected agent. Returns (agent, tier) where tier is 'warm' or 'cold'."""
        async with self._allocation_lock:
            try:
                agent = self._warm_pool.get_nowait()
                self._metrics["allocations"]["warm"] += 1
                self._metrics["last_updated"] = time.time()
                return agent, "warm"
            except asyncio.QueueEmpty:
                pass

        # Cold path: connect on-demand (no lock held)
        agent = await self._create_connected_agent()
        self._metrics["allocations"]["cold"] += 1
        self._metrics["last_updated"] = time.time()
        return agent, "cold"

    async def release_agent(self, agent: AzureLiveVoiceAgent) -> None:
        """
        Release agent after use. Safe default is to close and replenish.

        We intentionally avoid reusing the same connection across sessions to prevent
        cross-session state bleed. Instead, close and create a fresh warm agent in
        the background to maintain pool capacity.
        """
        try:
            await asyncio.to_thread(agent.close)
        except Exception as e:
            logger.debug(f"Agent close failed (ignored): {e}")

        # Refill warm pool in background
        asyncio.create_task(self._create_and_add_warm_agent(tag="refill-release"))

    async def shutdown(self) -> None:
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        logger.info("Shutting down Voice Live pool...")
        if self._prewarming_task:
            self._prewarming_task.cancel()
            try:
                await self._prewarming_task
            except asyncio.CancelledError:
                pass

        # Drain and close any warm agents
        while not self._warm_pool.empty():
            try:
                agent = self._warm_pool.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await asyncio.to_thread(agent.close)
            except Exception:
                pass

        logger.info("✅ Voice Live pool shutdown complete")

    # ---------------------------- internals ---------------------------- #
    async def _create_connected_agent(self) -> AzureLiveVoiceAgent:
        agent = build_lva_from_yaml(self._agent_yaml, enable_audio_io=False)
        await asyncio.to_thread(agent.connect)
        logger.debug("Connected new Voice Live agent")
        return agent

    async def _create_and_add_warm_agent(self, tag: str) -> None:
        try:
            agent = await self._create_connected_agent()
            await self._warm_pool.put(agent)
            logger.debug(f"Warm agent added (tag={tag})")
        except Exception as e:
            logger.error(f"Failed to add warm agent (tag={tag}): {e}")

    async def _prewarm_initial(self) -> None:
        target = self._warm_pool_size
        logger.info(f"Pre-warming Voice Live pool with {target} connections")
        tasks = [
            asyncio.create_task(self._create_and_add_warm_agent(tag=f"init-{i}"))
            for i in range(target)
        ]

        # Process in batches
        for i in range(0, len(tasks), self._prewarming_batch_size):
            batch = tasks[i : i + self._prewarming_batch_size]
            await asyncio.gather(*batch, return_exceptions=True)
            if i + self._prewarming_batch_size < len(tasks):
                await asyncio.sleep(0.1)

        logger.info(
            f"✅ Voice Live pre-warming complete: {self._warm_pool.qsize()}/{self._warm_pool_size} ready"
        )

    async def _prewarming_loop(self) -> None:
        while not self._is_shutting_down:
            try:
                size = self._warm_pool.qsize()
                deficit = self._warm_pool_size - size
                if deficit > 0:
                    logger.debug(
                        f"Replenishing Voice Live warm pool: {size}/{self._warm_pool_size} (+{deficit})"
                    )
                    for i in range(0, deficit, self._prewarming_batch_size):
                        batch_sz = min(self._prewarming_batch_size, deficit - i)
                        batch = [
                            self._create_and_add_warm_agent(tag=f"repl-{i+j}")
                            for j in range(batch_sz)
                        ]
                        await asyncio.gather(*batch, return_exceptions=True)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Voice Live prewarming loop: {e}")
                await asyncio.sleep(60)

    async def get_metrics(self) -> Dict[str, Any]:
        self._metrics["pool"]["warm_size"] = self._warm_pool.qsize()
        self._metrics["last_updated"] = time.time()
        return self._metrics


# Global helper
_global_voice_live_pool: Optional[VoiceLiveAgentPool] = None


async def get_voice_live_pool(*, background_prewarm: bool = False) -> VoiceLiveAgentPool:
    global _global_voice_live_pool
    if _global_voice_live_pool is None:
        _global_voice_live_pool = VoiceLiveAgentPool()
        await _global_voice_live_pool.initialize(background_prewarm=background_prewarm)
    return _global_voice_live_pool


async def cleanup_voice_live_pool() -> None:
    global _global_voice_live_pool
    if _global_voice_live_pool is not None:
        await _global_voice_live_pool.shutdown()
        _global_voice_live_pool = None

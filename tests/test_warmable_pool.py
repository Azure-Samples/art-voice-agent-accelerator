"""
Test suite for WarmableResourcePool.

Tests cover:
- Basic pool operations (acquire/release)
- Warm pool pre-warming and allocation tiers
- Session awareness and caching
- Background warmup task
- Warmup function (warm_fn) integration
- Metrics tracking
- Lifecycle management (prepare/shutdown)
- Edge cases and error handling
"""

import asyncio

import pytest
from src.pools.on_demand_pool import AllocationTier
from src.pools.warmable_pool import WarmableResourcePool


class MockResource:
    """Simple mock resource for testing."""

    def __init__(self, value: str = "test"):
        self.value = value
        self.id = id(self)
        self.is_ready = True
        self.warmed = False

    def __repr__(self) -> str:
        return f"MockResource({self.value}, warmed={self.warmed})"


async def mock_factory() -> MockResource:
    """Factory that creates mock resources."""
    await asyncio.sleep(0.001)  # Simulate small async delay
    return MockResource("factory-created")


async def mock_warm_fn(resource: MockResource) -> bool:
    """Warmup function that marks resource as warmed."""
    await asyncio.sleep(0.001)
    resource.warmed = True
    return True


async def mock_failing_warm_fn(resource: MockResource) -> bool:
    """Warmup function that always fails."""
    await asyncio.sleep(0.001)
    return False


# ---------- Basic Pool Operations ----------


@pytest.mark.asyncio
async def test_pool_init_defaults():
    """Test pool initialization with default values."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
    )
    assert pool._name == "test-pool"
    assert pool._warm_pool_size == 0
    assert pool._session_awareness is False
    assert pool._enable_background_warmup is False
    assert pool.session_awareness_enabled is False


@pytest.mark.asyncio
async def test_pool_prepare_without_warmup():
    """Test prepare() with no warm pool (OnDemand behavior)."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=0,
    )
    await pool.prepare()
    assert pool._ready.is_set()
    assert pool._warm_queue.qsize() == 0
    await pool.shutdown()


@pytest.mark.asyncio
async def test_pool_prepare_with_warmup():
    """Test prepare() pre-warms resources."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=3,
    )
    await pool.prepare()
    assert pool._ready.is_set()
    assert pool._warm_queue.qsize() == 3
    await pool.shutdown()


@pytest.mark.asyncio
async def test_pool_shutdown():
    """Test shutdown clears all resources."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        session_awareness=True,
    )
    await pool.prepare()

    # Add a session resource
    await pool.acquire_for_session("session-1")

    # Shutdown
    await pool.shutdown()

    assert not pool._ready.is_set()
    assert pool._warm_queue.qsize() == 0
    assert len(pool._session_cache) == 0


# ---------- Acquire/Release Operations ----------


@pytest.mark.asyncio
async def test_acquire_cold_when_no_warm_pool():
    """Test acquire returns cold resource when warm pool is empty."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=0,
    )
    await pool.prepare()

    resource = await pool.acquire()
    assert resource is not None
    assert resource.value == "factory-created"
    assert pool._metrics.allocations_cold == 1
    assert pool._metrics.allocations_warm == 0

    await pool.shutdown()


@pytest.mark.asyncio
async def test_acquire_warm_from_pool():
    """Test acquire returns warm resource when available."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
    )
    await pool.prepare()
    assert pool._warm_queue.qsize() == 2

    resource = await pool.acquire()
    assert resource is not None
    assert pool._metrics.allocations_warm == 1
    assert pool._metrics.allocations_cold == 0
    assert pool._warm_queue.qsize() == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_acquire_falls_back_to_cold():
    """Test acquire falls back to cold when warm pool exhausted."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=1,
    )
    await pool.prepare()

    # First acquire - warm
    r1 = await pool.acquire()
    assert pool._metrics.allocations_warm == 1

    # Second acquire - cold (pool exhausted)
    r2 = await pool.acquire()
    assert pool._metrics.allocations_cold == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_release_returns_to_warm_pool():
    """Test release returns resource to warm pool if space available."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
    )
    await pool.prepare()
    assert pool._warm_queue.qsize() == 2

    # Acquire all
    r1 = await pool.acquire()
    r2 = await pool.acquire()
    assert pool._warm_queue.qsize() == 0

    # Release one
    await pool.release(r1)
    assert pool._warm_queue.qsize() == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_release_discards_when_pool_full():
    """Test release discards resource when pool is full."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=1,
    )
    await pool.prepare()

    # Pool is already full (1 warm resource)
    assert pool._warm_queue.qsize() == 1

    # Create extra resource and try to release
    extra = MockResource("extra")
    await pool.release(extra)

    # Pool should still be at capacity
    assert pool._warm_queue.qsize() == 1

    await pool.shutdown()


# ---------- Session Awareness ----------


@pytest.mark.asyncio
async def test_session_awareness_disabled():
    """Test acquire_for_session with session_awareness=False."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=False,
    )
    await pool.prepare()

    r1, tier1 = await pool.acquire_for_session("session-1")
    r2, tier2 = await pool.acquire_for_session("session-1")

    # Without session awareness, should get different resources
    assert r1.id != r2.id
    assert pool.active_sessions == 0

    await pool.shutdown()


@pytest.mark.asyncio
async def test_session_awareness_caching():
    """Test session resources are cached and reused."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    r1, tier1 = await pool.acquire_for_session("session-1")
    r2, tier2 = await pool.acquire_for_session("session-1")

    # Same session should get same resource
    assert r1.id == r2.id
    assert tier2 == AllocationTier.DEDICATED
    assert pool._metrics.allocations_dedicated == 1
    assert pool.active_sessions == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_session_isolation():
    """Test different sessions get different resources."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    r1, _ = await pool.acquire_for_session("session-1")
    r2, _ = await pool.acquire_for_session("session-2")

    assert r1.id != r2.id
    assert pool.active_sessions == 2

    await pool.shutdown()


@pytest.mark.asyncio
async def test_release_for_session():
    """Test release_for_session removes from cache."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    r1, _ = await pool.acquire_for_session("session-1")
    assert pool.active_sessions == 1

    removed = await pool.release_for_session("session-1")
    assert removed is True
    assert pool.active_sessions == 0

    # Second release should return False
    removed = await pool.release_for_session("session-1")
    assert removed is False

    await pool.shutdown()


@pytest.mark.asyncio
async def test_session_stale_resource_replaced():
    """Test stale session resources are replaced."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    r1, _ = await pool.acquire_for_session("session-1")
    r1.is_ready = False  # Mark as stale

    r2, tier = await pool.acquire_for_session("session-1")

    # Should get a new resource
    assert r1.id != r2.id
    assert tier != AllocationTier.DEDICATED

    await pool.shutdown()


# ---------- Warmup Function ----------


@pytest.mark.asyncio
async def test_warm_fn_called_on_create():
    """Test warm_fn is called when creating resources."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        warm_fn=mock_warm_fn,
    )
    await pool.prepare()

    # All pre-warmed resources should be warmed
    r1 = await pool.acquire()
    assert r1.warmed is True

    r2 = await pool.acquire()
    assert r2.warmed is True

    await pool.shutdown()


@pytest.mark.asyncio
async def test_warm_fn_called_on_cold_create():
    """Test warm_fn is called for cold-created resources."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=0,  # No pre-warming
        warm_fn=mock_warm_fn,
    )
    await pool.prepare()

    resource = await pool.acquire()
    assert resource.warmed is True
    assert pool._metrics.allocations_cold == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_warm_fn_failure_tracked():
    """Test warmup failures are tracked in metrics."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        warm_fn=mock_failing_warm_fn,
    )
    await pool.prepare()

    # Resources should still be created even if warmup fails
    assert pool._warm_queue.qsize() == 2
    assert pool._metrics.warmup_failures == 2

    await pool.shutdown()


@pytest.mark.asyncio
async def test_warm_fn_exception_handled():
    """Test warmup exceptions are handled gracefully."""

    async def raising_warm_fn(r: MockResource) -> bool:
        raise RuntimeError("Warmup error")

    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=1,
        warm_fn=raising_warm_fn,
    )
    await pool.prepare()

    # Resource should still be available despite warmup exception
    assert pool._warm_queue.qsize() == 1
    assert pool._metrics.warmup_failures == 1

    await pool.shutdown()


# ---------- Background Warmup ----------


@pytest.mark.asyncio
async def test_background_warmup_disabled_by_default():
    """Test background warmup is disabled when not configured."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        enable_background_warmup=False,
    )
    await pool.prepare()

    assert pool._background_task is None

    await pool.shutdown()


@pytest.mark.asyncio
async def test_background_warmup_starts():
    """Test background warmup task starts when enabled."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        enable_background_warmup=True,
        warmup_interval_sec=0.1,
    )
    await pool.prepare()

    assert pool._background_task is not None
    assert not pool._background_task.done()

    await pool.shutdown()
    assert pool._background_task.done()


@pytest.mark.asyncio
async def test_background_warmup_refills_pool():
    """Test background warmup refills the pool."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        enable_background_warmup=True,
        warmup_interval_sec=0.05,
    )
    await pool.prepare()
    assert pool._warm_queue.qsize() == 2

    # Exhaust the pool
    await pool.acquire()
    await pool.acquire()
    assert pool._warm_queue.qsize() == 0

    # Wait for background refill
    await asyncio.sleep(0.15)

    assert pool._warm_queue.qsize() == 2
    assert pool._metrics.warmup_cycles >= 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_stale_session_cleanup():
    """Test stale sessions are cleaned up by background task."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
        session_max_age_sec=0.05,  # Very short for testing
        enable_background_warmup=True,
        warmup_interval_sec=0.05,
        warm_pool_size=1,
    )
    await pool.prepare()

    # Add session
    await pool.acquire_for_session("session-1")
    assert pool.active_sessions == 1

    # Wait for cleanup
    await asyncio.sleep(0.15)

    assert pool.active_sessions == 0

    await pool.shutdown()


# ---------- Metrics and Snapshot ----------


@pytest.mark.asyncio
async def test_snapshot_contents():
    """Test snapshot returns expected fields."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=2,
        session_awareness=True,
        enable_background_warmup=True,
    )
    await pool.prepare()

    # Acquire one resource
    await pool.acquire()

    snapshot = pool.snapshot()

    assert snapshot["name"] == "test-pool"
    assert snapshot["ready"] is True
    assert snapshot["warm_pool_size"] == 1
    assert snapshot["warm_pool_target"] == 2
    assert snapshot["session_awareness"] is True
    assert snapshot["background_warmup"] is True
    assert "metrics" in snapshot
    assert snapshot["metrics"]["allocations_total"] == 1

    await pool.shutdown()


@pytest.mark.asyncio
async def test_metrics_tracking():
    """Test all allocation tiers are tracked correctly."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=1,
        session_awareness=True,
    )
    await pool.prepare()

    # Warm allocation
    r1 = await pool.acquire()
    assert pool._metrics.allocations_warm == 1

    # Cold allocation (pool exhausted)
    r2 = await pool.acquire()
    assert pool._metrics.allocations_cold == 1

    # Dedicated allocation
    await pool.acquire_for_session("session-1")
    await pool.acquire_for_session("session-1")  # Returns cached
    assert pool._metrics.allocations_dedicated == 1

    assert pool._metrics.allocations_total == 4

    await pool.shutdown()


# ---------- Edge Cases ----------


@pytest.mark.asyncio
async def test_acquire_with_none_session_id():
    """Test acquire_for_session with None session_id."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    r1, tier = await pool.acquire_for_session(None)
    r2, tier = await pool.acquire_for_session(None)

    # Should get different resources (no caching for None)
    assert r1.id != r2.id
    assert pool.active_sessions == 0

    await pool.shutdown()


@pytest.mark.asyncio
async def test_release_none_resource():
    """Test release handles None gracefully."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
    )
    await pool.prepare()

    # Should not raise
    await pool.release(None)

    await pool.shutdown()


@pytest.mark.asyncio
async def test_concurrent_acquires():
    """Test concurrent acquire operations."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        warm_pool_size=5,
    )
    await pool.prepare()

    # Concurrent acquires
    resources = await asyncio.gather(*[pool.acquire() for _ in range(10)])

    assert len(resources) == 10
    assert pool._metrics.allocations_warm == 5
    assert pool._metrics.allocations_cold == 5

    await pool.shutdown()


@pytest.mark.asyncio
async def test_concurrent_session_acquires():
    """Test concurrent session acquire operations stabilize to cached resource."""
    pool = WarmableResourcePool(
        factory=mock_factory,
        name="test-pool",
        session_awareness=True,
    )
    await pool.prepare()

    # First acquire establishes the session cache
    r1, _ = await pool.acquire_for_session("session-1")

    # Subsequent concurrent acquires should all get the cached resource
    results = await asyncio.gather(*[pool.acquire_for_session("session-1") for _ in range(5)])

    # All should get the same cached resource
    resource_ids = {r.id for r, _ in results}
    assert len(resource_ids) == 1
    assert r1.id in resource_ids

    # All should be DEDICATED tier
    tiers = {tier for _, tier in results}
    assert tiers == {AllocationTier.DEDICATED}

    await pool.shutdown()

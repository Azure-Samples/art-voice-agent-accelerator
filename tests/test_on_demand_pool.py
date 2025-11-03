"""
Test suite for OnDemandResourcePool.

Tests cover:
- Basic factory operations and resource creation
- Session awareness and caching behavior  
- Metrics tracking and telemetry
- Lifecycle management (prepare/shutdown)
- Concurrent access patterns
- Error handling scenarios
- Pool snapshot functionality
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch
from typing import Any, Dict

from src.pools.on_demand_pool import OnDemandResourcePool, _ProviderMetrics
from src.pools.async_pool import AllocationTier


class MockResource:
    """Simple mock resource for testing."""
    
    def __init__(self, value: str = "test"):
        self.value = value
        self.id = id(self)
    
    def __eq__(self, other):
        return isinstance(other, MockResource) and self.id == other.id
    
    def __repr__(self):
        return f"MockResource(value={self.value}, id={self.id})"


@pytest.fixture
async def simple_factory():
    """Simple async factory that creates MockResource instances."""
    async def factory():
        await asyncio.sleep(0.001)  # Simulate async work
        return MockResource()
    return factory


@pytest.fixture
async def failing_factory():
    """Factory that always raises an exception."""
    async def factory():
        raise ValueError("Factory failed")
    return factory


@pytest.fixture
async def counter_factory():
    """Factory that tracks creation count."""
    count = {"value": 0}
    
    async def factory():
        count["value"] += 1
        await asyncio.sleep(0.001)
        return MockResource(f"resource-{count['value']}")
    
    factory.count = count
    return factory


class TestOnDemandResourcePool:
    """Test suite for OnDemandResourcePool functionality."""

    async def test_basic_initialization(self, simple_factory):
        """Test basic pool initialization."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=False,
            name="test-pool"
        )
        
        assert pool._name == "test-pool"
        assert pool._session_awareness is False
        assert not pool._ready.is_set()
        assert pool.session_awareness_enabled is False
        assert pool.active_sessions == 0

    async def test_prepare_and_shutdown_lifecycle(self, simple_factory):
        """Test pool lifecycle management."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=True,
            name="test-pool"
        )
        
        # Initially not ready
        assert not pool._ready.is_set()
        
        # Prepare should mark ready
        await pool.prepare()
        assert pool._ready.is_set()
        
        # Add some session data
        resource, tier = await pool.acquire_for_session("session-1")
        assert tier == AllocationTier.COLD
        assert pool.active_sessions == 1
        
        # Shutdown should clear everything
        await pool.shutdown()
        assert not pool._ready.is_set()
        assert pool.active_sessions == 0
        assert len(pool._session_cache) == 0

    async def test_acquire_without_session_awareness(self, counter_factory):
        """Test basic acquire operations without session awareness."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=False,
            name="test-pool"
        )
        
        # Each acquire should create a new resource
        resource1 = await pool.acquire()
        resource2 = await pool.acquire()
        
        assert resource1 != resource2
        assert counter_factory.count["value"] == 2
        assert pool._metrics.allocations_total == 2
        assert pool._metrics.allocations_new == 2
        assert pool._metrics.allocations_cached == 0

    async def test_acquire_for_session_without_awareness(self, counter_factory):
        """Test session acquire when session awareness is disabled."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=False,
            name="test-pool"
        )
        
        # Should always return new resources and COLD tier
        resource1, tier1 = await pool.acquire_for_session("session-1")
        resource2, tier2 = await pool.acquire_for_session("session-1")
        
        assert resource1 != resource2
        assert tier1 == AllocationTier.COLD
        assert tier2 == AllocationTier.COLD
        assert counter_factory.count["value"] == 2
        assert pool.active_sessions == 0  # No caching

    async def test_session_awareness_caching(self, counter_factory):
        """Test session-aware caching behavior."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="test-pool"
        )
        
        # First acquire should create and cache
        resource1, tier1 = await pool.acquire_for_session("session-1")
        assert tier1 == AllocationTier.COLD
        assert pool.active_sessions == 1
        assert counter_factory.count["value"] == 1
        
        # Second acquire for same session should return cached
        resource2, tier2 = await pool.acquire_for_session("session-1")
        assert resource1 == resource2
        assert tier2 == AllocationTier.DEDICATED
        assert pool.active_sessions == 1
        assert counter_factory.count["value"] == 1  # No new creation
        
        # Different session should create new resource
        resource3, tier3 = await pool.acquire_for_session("session-2")
        assert resource3 != resource1
        assert tier3 == AllocationTier.COLD
        assert pool.active_sessions == 2
        assert counter_factory.count["value"] == 2

    async def test_session_awareness_with_none_session_id(self, counter_factory):
        """Test session awareness with None session ID."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="test-pool"
        )
        
        # None session ID should behave like no session awareness
        resource1, tier1 = await pool.acquire_for_session(None)
        resource2, tier2 = await pool.acquire_for_session(None)
        
        assert resource1 != resource2
        assert tier1 == AllocationTier.COLD
        assert tier2 == AllocationTier.COLD
        assert pool.active_sessions == 0
        assert counter_factory.count["value"] == 2

    async def test_release_operations(self, simple_factory):
        """Test resource release operations."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=True,
            name="test-pool"
        )
        
        # Basic release is no-op
        resource = await pool.acquire()
        result = await pool.release(resource)
        assert result is None
        
        # Release for session with no awareness should return True
        pool._session_awareness = False
        result = await pool.release_for_session("session-1", resource)
        assert result is True
        
        # Release for session with awareness
        pool._session_awareness = True
        resource, _ = await pool.acquire_for_session("session-1")
        assert pool.active_sessions == 1
        
        # Release existing session
        result = await pool.release_for_session("session-1", resource)
        assert result is True
        assert pool.active_sessions == 0
        
        # Release non-existent session
        result = await pool.release_for_session("session-2", resource)
        assert result is False

    async def test_metrics_tracking(self, counter_factory):
        """Test comprehensive metrics tracking."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="test-pool"
        )
        
        # Initial metrics
        assert pool._metrics.allocations_total == 0
        assert pool._metrics.allocations_new == 0
        assert pool._metrics.allocations_cached == 0
        assert pool._metrics.active_sessions == 0
        
        # First session acquire
        await pool.acquire_for_session("session-1")
        assert pool._metrics.allocations_total == 1
        assert pool._metrics.allocations_new == 1
        assert pool._metrics.allocations_cached == 0
        assert pool._metrics.active_sessions == 1
        
        # Cached acquire
        await pool.acquire_for_session("session-1")
        assert pool._metrics.allocations_total == 2
        assert pool._metrics.allocations_new == 1
        assert pool._metrics.allocations_cached == 1
        assert pool._metrics.active_sessions == 1
        
        # New session
        await pool.acquire_for_session("session-2")
        assert pool._metrics.allocations_total == 3
        assert pool._metrics.allocations_new == 2
        assert pool._metrics.allocations_cached == 1
        assert pool._metrics.active_sessions == 2
        
        # Basic acquire (no session)
        await pool.acquire()
        assert pool._metrics.allocations_total == 4
        assert pool._metrics.allocations_new == 3
        assert pool._metrics.allocations_cached == 1

    async def test_snapshot_functionality(self, simple_factory):
        """Test pool snapshot for diagnostics."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=True,
            name="diagnostic-pool"
        )
        
        # Prepare pool
        await pool.prepare()
        
        # Add some sessions
        await pool.acquire_for_session("session-1")
        await pool.acquire_for_session("session-2")
        
        # Get snapshot
        snapshot = pool.snapshot()
        
        assert snapshot["name"] == "diagnostic-pool"
        assert snapshot["ready"] is True
        assert snapshot["session_awareness"] is True
        assert snapshot["active_sessions"] == 2
        
        metrics = snapshot["metrics"]
        assert metrics["allocations_total"] == 2
        assert metrics["allocations_new"] == 2
        assert metrics["allocations_cached"] == 0
        assert metrics["active_sessions"] == 2
        assert "timestamp" in metrics
        assert isinstance(metrics["timestamp"], float)

    async def test_concurrent_access(self, counter_factory):
        """Test concurrent access patterns."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="concurrent-pool"
        )
        
        # Concurrent acquires for same session
        tasks = [
            pool.acquire_for_session("session-1"),
            pool.acquire_for_session("session-1"),
            pool.acquire_for_session("session-1")
        ]
        
        results = await asyncio.gather(*tasks)
        
        # First should be COLD (new), others should be DEDICATED (cached)
        resources = [result[0] for result in results]
        tiers = [result[1] for result in results]
        
        # All should be the same resource (cached)
        assert all(r == resources[0] for r in resources)
        
        # First should be COLD, rest DEDICATED
        assert tiers[0] == AllocationTier.COLD
        assert all(t == AllocationTier.DEDICATED for t in tiers[1:])
        
        # Only one resource should have been created
        assert counter_factory.count["value"] == 1
        assert pool.active_sessions == 1

    async def test_concurrent_different_sessions(self, counter_factory):
        """Test concurrent access for different sessions."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="multi-session-pool"
        )
        
        # Concurrent acquires for different sessions
        tasks = [
            pool.acquire_for_session(f"session-{i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should be different resources
        resources = [result[0] for result in results]
        tiers = [result[1] for result in results]
        
        assert len(set(r.id for r in resources)) == 5  # All unique
        assert all(t == AllocationTier.COLD for t in tiers)  # All new
        assert counter_factory.count["value"] == 5
        assert pool.active_sessions == 5

    async def test_factory_error_handling(self, failing_factory):
        """Test handling of factory errors."""
        pool = OnDemandResourcePool(
            factory=failing_factory,
            session_awareness=True,
            name="error-pool"
        )
        
        # Acquire should propagate factory errors
        with pytest.raises(ValueError, match="Factory failed"):
            await pool.acquire()
        
        with pytest.raises(ValueError, match="Factory failed"):
            await pool.acquire_for_session("session-1")
        
        # Metrics should be updated for the calls that were attempted
        # Note: The current implementation updates metrics before calling factory,
        # so successful metrics updates depend on the implementation details
        assert pool._metrics.allocations_total >= 1  # At least one attempt was made

    async def test_timeout_parameter_ignored(self, simple_factory):
        """Test that timeout parameters are ignored (but accepted for compatibility)."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=False,
            name="timeout-pool"
        )
        
        # These should work normally despite timeout being ignored
        resource1 = await pool.acquire(timeout=1.0)
        resource2, tier = await pool.acquire_for_session("session-1", timeout=5.0)
        
        assert resource1 is not None
        assert resource2 is not None
        assert tier == AllocationTier.COLD

    async def test_property_access(self, simple_factory):
        """Test property accessors."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=True,
            name="property-pool"
        )
        
        assert pool.session_awareness_enabled is True
        assert pool.active_sessions == 0
        
        # Add sessions
        await pool.acquire_for_session("session-1")
        await pool.acquire_for_session("session-2")
        
        assert pool.active_sessions == 2
        
        # Disable session awareness
        pool._session_awareness = False
        assert pool.session_awareness_enabled is False

    async def test_empty_session_id_handling(self, counter_factory):
        """Test handling of empty string session IDs."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="empty-session-pool"
        )
        
        # Empty string should be treated like None
        resource1, tier1 = await pool.acquire_for_session("")
        resource2, tier2 = await pool.acquire_for_session("")
        
        assert resource1 != resource2
        assert tier1 == AllocationTier.COLD
        assert tier2 == AllocationTier.COLD
        assert pool.active_sessions == 0
        assert counter_factory.count["value"] == 2

    async def test_release_session_with_none_session_id(self, simple_factory):
        """Test release_for_session with None session ID."""
        pool = OnDemandResourcePool(
            factory=simple_factory,
            session_awareness=True,
            name="release-none-pool"
        )
        
        resource = await pool.acquire()
        
        # Release with None session ID should return True
        result = await pool.release_for_session(None, resource)
        assert result is True
        
        # Release with empty string should also return True
        result = await pool.release_for_session("", resource)
        assert result is True

    async def test_metrics_dataclass_functionality(self):
        """Test _ProviderMetrics dataclass behavior."""
        metrics = _ProviderMetrics()
        
        # Test default values
        assert metrics.allocations_total == 0
        assert metrics.allocations_cached == 0
        assert metrics.allocations_new == 0
        assert metrics.active_sessions == 0
        
        # Test modification
        metrics.allocations_total = 10
        metrics.allocations_cached = 3
        metrics.allocations_new = 7
        metrics.active_sessions = 5
        
        # Test asdict conversion
        metrics_dict = metrics.__dict__
        expected = {
            'allocations_total': 10,
            'allocations_cached': 3, 
            'allocations_new': 7,
            'active_sessions': 5
        }
        assert metrics_dict == expected


@pytest.mark.asyncio
class TestOnDemandPoolIntegration:
    """Integration tests for OnDemandResourcePool with realistic scenarios."""

    async def test_realistic_tts_pool_usage(self):
        """Test realistic TTS client pool usage pattern."""
        
        class MockTTSClient:
            def __init__(self, voice_name: str = "default"):
                self.voice_name = voice_name
                self.id = id(self)
            
            async def synthesize(self, text: str) -> bytes:
                await asyncio.sleep(0.01)  # Simulate synthesis
                return f"synthesized-{text}".encode()
        
        async def tts_factory():
            await asyncio.sleep(0.005)  # Simulate client creation
            return MockTTSClient()
        
        pool = OnDemandResourcePool(
            factory=tts_factory,
            session_awareness=True,
            name="tts-pool"
        )
        
        await pool.prepare()
        
        # Simulate conversation session lifecycle
        session_id = "conversation-session-123"
        
        # Acquire TTS client for session
        tts_client, tier = await pool.acquire_for_session(session_id)
        assert tier == AllocationTier.COLD
        assert isinstance(tts_client, MockTTSClient)
        
        # Use the client multiple times (cached)
        for i in range(3):
            cached_client, tier = await pool.acquire_for_session(session_id)
            assert cached_client == tts_client
            assert tier == AllocationTier.DEDICATED
            
            # Simulate usage
            result = await cached_client.synthesize(f"Hello {i}")
            assert result == f"synthesized-Hello {i}".encode()
        
        # Verify metrics
        snapshot = pool.snapshot()
        assert snapshot["active_sessions"] == 1
        metrics = snapshot["metrics"]
        assert metrics["allocations_total"] == 4  # 1 new + 3 cached
        assert metrics["allocations_new"] == 1
        assert metrics["allocations_cached"] == 3
        
        # Release session
        released = await pool.release_for_session(session_id)
        assert released is True
        assert pool.active_sessions == 0

    async def test_realistic_stt_pool_usage(self):
        """Test realistic STT client pool usage pattern."""
        
        class MockSTTClient:
            def __init__(self):
                self.id = id(self)
                self.callbacks = {}
                self.running = False
            
            def set_partial_result_callback(self, callback):
                self.callbacks['partial'] = callback
            
            def set_final_result_callback(self, callback):
                self.callbacks['final'] = callback
            
            def start(self):
                self.running = True
            
            def stop(self):
                self.running = False
        
        async def stt_factory():
            await asyncio.sleep(0.005)  # Simulate client creation
            return MockSTTClient()
        
        pool = OnDemandResourcePool(
            factory=stt_factory,
            session_awareness=True,
            name="stt-pool"
        )
        
        await pool.prepare()
        
        # Multiple concurrent sessions
        sessions = ["session-1", "session-2", "session-3"]
        
        clients = {}
        for session_id in sessions:
            client, tier = await pool.acquire_for_session(session_id)
            assert tier == AllocationTier.COLD
            clients[session_id] = client
            
            # Configure callbacks
            client.set_partial_result_callback(lambda txt: print(f"Partial: {txt}"))
            client.set_final_result_callback(lambda txt: print(f"Final: {txt}"))
            client.start()
        
        # Verify each session gets same client on re-acquire
        for session_id in sessions:
            cached_client, tier = await pool.acquire_for_session(session_id)
            assert cached_client == clients[session_id]
            assert tier == AllocationTier.DEDICATED
            assert cached_client.running is True
        
        # Verify pool state
        assert pool.active_sessions == 3
        snapshot = pool.snapshot()
        metrics = snapshot["metrics"]
        assert metrics["allocations_total"] == 6  # 3 new + 3 cached
        assert metrics["allocations_new"] == 3
        assert metrics["allocations_cached"] == 3
        
        # Clean shutdown
        await pool.shutdown()
        assert pool.active_sessions == 0

    async def test_mixed_session_and_non_session_usage(self, counter_factory):
        """Test mixed usage patterns of session-aware and regular acquires."""
        pool = OnDemandResourcePool(
            factory=counter_factory,
            session_awareness=True,
            name="mixed-pool"
        )
        
        # Mix of session and non-session acquires
        resource1 = await pool.acquire()  # No session
        resource2, tier2 = await pool.acquire_for_session("session-1")
        resource3 = await pool.acquire()  # No session
        resource4, tier4 = await pool.acquire_for_session("session-1")  # Cached
        
        assert resource1 != resource2 != resource3
        assert resource2 == resource4  # Cached
        assert tier2 == AllocationTier.COLD
        assert tier4 == AllocationTier.DEDICATED
        
        assert pool.active_sessions == 1  # Only session-1
        assert counter_factory.count["value"] == 3  # 3 unique resources
        
        # Verify metrics
        metrics = pool._metrics
        assert metrics.allocations_total == 4
        assert metrics.allocations_new == 3
        assert metrics.allocations_cached == 1
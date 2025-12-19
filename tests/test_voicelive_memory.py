"""
Tests for VoiceLive handler and orchestrator memory management.

These tests verify that VoiceLive sessions properly clean up resources
to prevent memory leaks across multiple sessions.
"""

import asyncio
import gc
import tracemalloc
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


class FakeState:
    """Fake WebSocket state."""

    def __init__(self):
        self.session_id = "test-session-123"
        self.call_connection_id = "test-call-123"
        self.scenario = None
        self.cm = None
        self.voice_live_handler = None


class FakeApp:
    """Fake FastAPI app with state."""

    def __init__(self):
        self.state = MagicMock()
        self.state.unified_agents = {}
        self.state.handoff_map = {}
        self.state.redis = MagicMock()


class FakeWebSocket:
    """Minimal fake WebSocket for testing."""

    def __init__(self):
        self.sent = []
        self.state = FakeState()
        self.app = FakeApp()
        self._connected = True

    async def send_text(self, text: str):
        await asyncio.sleep(0)
        self.sent.append(text)

    async def send_json(self, data: dict):
        await asyncio.sleep(0)
        self.sent.append(data)


class FakeVoiceLiveAgent:
    """Fake VoiceLive agent adapter."""

    def __init__(self, name: str):
        self.name = name
        self.description = f"Test agent: {name}"
        self._greeting = f"Hello from {name}"
        self._return_greeting = f"Welcome back to {name}"
        self.voice_name = "en-US-JennyNeural"
        self.voice_type = "azure"
        self.tools = []
        self.modalities = []
        self.turn_detection = None
        self.tool_choice = "auto"

    def render_greeting(self, context=None):
        return self._greeting

    def render_return_greeting(self, context=None):
        return self._return_greeting

    async def apply_session(self, conn, **kwargs):
        await asyncio.sleep(0)

    async def trigger_response(self, conn, **kwargs):
        await asyncio.sleep(0)


class FakeVoiceLiveConnection:
    """Fake VoiceLive SDK connection."""

    def __init__(self):
        self.session = MagicMock()
        self.session.update = AsyncMock()
        self.response = MagicMock()
        self.response.cancel = AsyncMock()
        self.conversation = MagicMock()
        self.conversation.item = MagicMock()
        self.conversation.item.create = AsyncMock()
        self._closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._closed = True

    async def send(self, event):
        await asyncio.sleep(0)


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestLiveOrchestratorCleanup:
    """Test LiveOrchestrator cleanup method."""

    def _create_orchestrator(self):
        """Create a test orchestrator instance."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {
            "Concierge": FakeVoiceLiveAgent("Concierge"),
            "Advisor": FakeVoiceLiveAgent("Advisor"),
        }
        handoff_map = {"handoff_to_advisor": "Advisor"}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map=handoff_map,
            start_agent="Concierge",
            messenger=MagicMock(),
            call_connection_id="test-call-123",
        )

        # Add some state to verify cleanup
        orchestrator.visited_agents.add("Concierge")
        orchestrator._user_message_history.append("Hello")
        orchestrator._user_message_history.append("How are you?")
        orchestrator._last_user_message = "How are you?"
        orchestrator._last_assistant_message = "I'm doing well!"
        orchestrator._system_vars["client_id"] = "client-123"

        return orchestrator

    def test_cleanup_clears_agents(self):
        """Verify cleanup() clears agents registry."""
        orchestrator = self._create_orchestrator()
        assert len(orchestrator.agents) == 2

        orchestrator.cleanup()

        assert orchestrator.agents == {}

    def test_cleanup_clears_handoff_map(self):
        """Verify cleanup() clears handoff map."""
        orchestrator = self._create_orchestrator()
        assert len(orchestrator._handoff_map) == 1

        orchestrator.cleanup()

        assert orchestrator._handoff_map == {}

    def test_cleanup_clears_connection(self):
        """Verify cleanup() clears connection reference."""
        orchestrator = self._create_orchestrator()
        assert orchestrator.conn is not None

        orchestrator.cleanup()

        assert orchestrator.conn is None

    def test_cleanup_clears_messenger(self):
        """Verify cleanup() clears messenger reference."""
        orchestrator = self._create_orchestrator()
        assert orchestrator.messenger is not None

        orchestrator.cleanup()

        assert orchestrator.messenger is None

    def test_cleanup_clears_user_message_history(self):
        """Verify cleanup() clears user message history."""
        orchestrator = self._create_orchestrator()
        assert len(orchestrator._user_message_history) == 2

        orchestrator.cleanup()

        assert len(orchestrator._user_message_history) == 0

    def test_cleanup_clears_visited_agents(self):
        """Verify cleanup() clears visited agents."""
        orchestrator = self._create_orchestrator()
        assert len(orchestrator.visited_agents) == 1

        orchestrator.cleanup()

        assert len(orchestrator.visited_agents) == 0

    def test_cleanup_clears_system_vars(self):
        """Verify cleanup() clears system vars."""
        orchestrator = self._create_orchestrator()
        assert "client_id" in orchestrator._system_vars

        orchestrator.cleanup()

        assert len(orchestrator._system_vars) == 0


class TestOrchestratorRegistry:
    """Test orchestrator registry functions."""

    def test_register_and_get(self):
        """Verify register and get work correctly."""
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            _voicelive_orchestrators,
            get_voicelive_orchestrator,
            register_voicelive_orchestrator,
            unregister_voicelive_orchestrator,
        )

        # Clear registry first
        _voicelive_orchestrators.clear()

        orchestrator = MagicMock()
        session_id = "test-session-registry"

        register_voicelive_orchestrator(session_id, orchestrator)

        result = get_voicelive_orchestrator(session_id)
        assert result is orchestrator

        # Cleanup
        unregister_voicelive_orchestrator(session_id)

    def test_unregister_removes_entry(self):
        """Verify unregister removes from registry."""
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            _voicelive_orchestrators,
            get_voicelive_orchestrator,
            register_voicelive_orchestrator,
            unregister_voicelive_orchestrator,
        )

        _voicelive_orchestrators.clear()

        orchestrator = MagicMock()
        session_id = "test-session-unregister"

        register_voicelive_orchestrator(session_id, orchestrator)
        unregister_voicelive_orchestrator(session_id)

        result = get_voicelive_orchestrator(session_id)
        assert result is None

    def test_stale_orchestrator_cleanup(self):
        """Verify stale orchestrators are cleaned up."""
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            _cleanup_stale_orchestrators,
            _voicelive_orchestrators,
            register_voicelive_orchestrator,
        )

        _voicelive_orchestrators.clear()

        # Create a stale orchestrator (conn=None, agents={})
        stale = MagicMock()
        stale.conn = None
        stale.agents = {}
        _voicelive_orchestrators["stale-session"] = stale

        # Create a valid orchestrator
        valid = MagicMock()
        valid.conn = MagicMock()
        valid.agents = {"Agent": MagicMock()}
        _voicelive_orchestrators["valid-session"] = valid

        # Cleanup should remove stale, keep valid
        removed = _cleanup_stale_orchestrators()

        assert removed == 1
        assert "stale-session" not in _voicelive_orchestrators
        assert "valid-session" in _voicelive_orchestrators

        # Cleanup
        _voicelive_orchestrators.clear()

    def test_registry_size_tracking(self):
        """Verify registry size can be tracked."""
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            _voicelive_orchestrators,
            get_orchestrator_registry_size,
            register_voicelive_orchestrator,
            unregister_voicelive_orchestrator,
        )

        _voicelive_orchestrators.clear()

        assert get_orchestrator_registry_size() == 0

        register_voicelive_orchestrator("s1", MagicMock())
        assert get_orchestrator_registry_size() == 1

        register_voicelive_orchestrator("s2", MagicMock())
        assert get_orchestrator_registry_size() == 2

        unregister_voicelive_orchestrator("s1")
        assert get_orchestrator_registry_size() == 1

        # Cleanup
        _voicelive_orchestrators.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND TASK TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestBackgroundTaskTracking:
    """Test background task tracking and cleanup."""

    @pytest.mark.asyncio
    async def test_background_task_tracked(self):
        """Verify background tasks are tracked in pending set."""
        from apps.artagent.backend.voice.voicelive.handler import (
            _background_task,
            _pending_background_tasks,
        )

        _pending_background_tasks.clear()

        async def dummy_coro():
            await asyncio.sleep(0.1)

        task = _background_task(dummy_coro(), label="test")

        assert task in _pending_background_tasks

        # Wait for completion
        await task
        await asyncio.sleep(0)

        # Should be removed after completion
        assert task not in _pending_background_tasks

    @pytest.mark.asyncio
    async def test_cancel_all_background_tasks(self):
        """Verify all background tasks can be cancelled."""
        from apps.artagent.backend.voice.voicelive.handler import (
            _background_task,
            _cancel_all_background_tasks,
            _pending_background_tasks,
        )

        _pending_background_tasks.clear()

        async def long_running():
            await asyncio.sleep(10)

        # Create several background tasks
        for i in range(5):
            _background_task(long_running(), label=f"task-{i}")

        assert len(_pending_background_tasks) == 5

        # Cancel all
        cancelled = _cancel_all_background_tasks()

        assert cancelled == 5
        assert len(_pending_background_tasks) == 0

    @pytest.mark.asyncio
    async def test_background_task_error_logging(self):
        """Verify background task errors are logged but don't crash."""
        from apps.artagent.backend.voice.voicelive.handler import (
            _background_task,
            _pending_background_tasks,
        )

        _pending_background_tasks.clear()

        async def failing_coro():
            raise ValueError("Test error")

        task = _background_task(failing_coro(), label="failing")

        # Wait for task to complete (with error)
        await asyncio.sleep(0.01)

        # Task should be removed even on error
        assert task not in _pending_background_tasks


# ═══════════════════════════════════════════════════════════════════════════════
# GREETING TASK TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGreetingTaskCleanup:
    """Test greeting task cancellation."""

    def _create_orchestrator_with_greeting_tasks(self):
        """Create orchestrator with pending greeting tasks."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Manually add some fake tasks to simulate greeting tasks
        async def fake_greeting():
            await asyncio.sleep(10)

        for i in range(3):
            task = asyncio.create_task(fake_greeting(), name=f"greeting-{i}")
            orchestrator._greeting_tasks.add(task)

        return orchestrator

    @pytest.mark.asyncio
    async def test_greeting_tasks_cancelled_on_cleanup(self):
        """Verify greeting tasks are cancelled during cleanup."""
        orchestrator = self._create_orchestrator_with_greeting_tasks()

        assert len(orchestrator._greeting_tasks) == 3

        orchestrator.cleanup()

        # All tasks should be cancelled
        assert len(orchestrator._greeting_tasks) == 0

    @pytest.mark.asyncio
    async def test_cancel_pending_greeting_tasks_method(self):
        """Verify _cancel_pending_greeting_tasks works correctly."""
        orchestrator = self._create_orchestrator_with_greeting_tasks()

        orchestrator._cancel_pending_greeting_tasks()

        assert len(orchestrator._greeting_tasks) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY LEAK DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryLeakPrevention:
    """Test memory leak prevention across multiple sessions."""

    @pytest.mark.asyncio
    async def test_no_unbounded_registry_growth(self):
        """Verify registry doesn't grow unboundedly with repeated sessions."""
        from apps.artagent.backend.voice.voicelive.orchestrator import (
            _voicelive_orchestrators,
            register_voicelive_orchestrator,
            unregister_voicelive_orchestrator,
        )

        _voicelive_orchestrators.clear()

        # Simulate many sessions
        for i in range(100):
            session_id = f"session-{i}"
            orchestrator = MagicMock()
            orchestrator.conn = MagicMock()
            orchestrator.agents = {"Agent": MagicMock()}

            register_voicelive_orchestrator(session_id, orchestrator)

            # Simulate session end
            unregister_voicelive_orchestrator(session_id)

        # Registry should be empty
        assert len(_voicelive_orchestrators) == 0

    @pytest.mark.asyncio
    async def test_orchestrator_gc_after_cleanup(self):
        """Verify orchestrator can be garbage collected after cleanup."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        gc.collect()

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Get a weak reference to track GC
        import weakref

        ref = weakref.ref(orchestrator)

        # Cleanup and delete
        orchestrator.cleanup()
        del orchestrator

        gc.collect()

        # Should be garbage collected
        assert ref() is None

    @pytest.mark.asyncio
    async def test_no_circular_refs_in_messenger(self):
        """Verify messenger cleanup breaks circular references."""
        from apps.artagent.backend.voice.voicelive.handler import _SessionMessenger

        ws = FakeWebSocket()
        messenger = _SessionMessenger(ws)

        # Verify cleanup is possible
        messenger._ws = None
        messenger._default_sender = None

        import weakref

        ref = weakref.ref(messenger)
        del messenger

        gc.collect()

        assert ref() is None

    @pytest.mark.asyncio
    async def test_repeated_orchestrator_lifecycle_memory(self):
        """Verify memory doesn't grow with repeated orchestrator creation/cleanup."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        tracemalloc.start()
        gc.collect()
        snapshot1 = tracemalloc.take_snapshot()

        # Create and cleanup many orchestrators
        for i in range(50):
            conn = FakeVoiceLiveConnection()
            agents = {
                "Concierge": FakeVoiceLiveAgent("Concierge"),
                "Advisor": FakeVoiceLiveAgent("Advisor"),
            }

            orchestrator = LiveOrchestrator(
                conn=conn,
                agents=agents,
                handoff_map={"handoff": "Advisor"},
                start_agent="Concierge",
            )

            # Simulate some usage
            orchestrator._user_message_history.append("Test message")
            orchestrator.visited_agents.add("Concierge")

            # Cleanup
            orchestrator.cleanup()
            del orchestrator

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()

        total1 = sum(s.size for s in snapshot1.statistics("filename"))
        total2 = sum(s.size for s in snapshot2.statistics("filename"))
        growth = total2 - total1

        tracemalloc.stop()

        # Allow some tolerance (500KB) for normal variations
        assert growth <= 500_000, f"Memory growth too large: {growth} bytes"


# ═══════════════════════════════════════════════════════════════════════════════
# USER MESSAGE HISTORY TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserMessageHistoryBounds:
    """Test user message history deque is properly bounded."""

    def test_user_message_history_bounded(self):
        """Verify user message history deque has maxlen."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Add more than maxlen messages
        for i in range(20):
            orchestrator._user_message_history.append(f"Message {i}")

        # Should be bounded to maxlen (5)
        assert len(orchestrator._user_message_history) == 5
        assert orchestrator._user_message_history[-1] == "Message 19"

        orchestrator.cleanup()

    def test_user_message_history_cleared_on_cleanup(self):
        """Verify user message history is cleared on cleanup."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        orchestrator._user_message_history.append("Test")
        assert len(orchestrator._user_message_history) == 1

        orchestrator.cleanup()

        assert len(orchestrator._user_message_history) == 0


__all__ = [
    "TestLiveOrchestratorCleanup",
    "TestOrchestratorRegistry",
    "TestBackgroundTaskTracking",
    "TestGreetingTaskCleanup",
    "TestMemoryLeakPrevention",
    "TestUserMessageHistoryBounds",
    "TestHotPathOptimization",
    "TestScenarioUpdate",
]


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO UPDATE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioUpdate:
    """Tests for scenario update functionality."""

    def test_update_scenario_updates_agents(self):
        """Verify update_scenario correctly updates agents registry."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        assert "Concierge" in orchestrator.agents
        assert "Banking" not in orchestrator.agents

        # Update with new scenario agents
        new_agents = {
            "Banking": FakeVoiceLiveAgent("Banking"),
            "Support": FakeVoiceLiveAgent("Support"),
        }
        orchestrator.update_scenario(
            agents=new_agents,
            handoff_map={"Banking": "Support"},
            start_agent="Banking",
        )

        assert "Banking" in orchestrator.agents
        assert "Support" in orchestrator.agents
        assert "Concierge" not in orchestrator.agents
        assert orchestrator.active == "Banking"

        orchestrator.cleanup()

    def test_update_scenario_switches_agent_when_not_in_new_scenario(self):
        """Verify update_scenario switches to start_agent when current agent is not in new scenario."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        assert orchestrator.active == "Concierge"

        # Update with new scenario where Concierge doesn't exist
        new_agents = {"InvestmentAdvisor": FakeVoiceLiveAgent("InvestmentAdvisor")}
        orchestrator.update_scenario(
            agents=new_agents,
            handoff_map={},
            start_agent="InvestmentAdvisor",
        )

        # Should have switched to InvestmentAdvisor
        assert orchestrator.active == "InvestmentAdvisor"

        orchestrator.cleanup()

    def test_update_scenario_keeps_agent_when_in_new_scenario(self):
        """Verify update_scenario keeps current agent when it exists in new scenario."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        assert orchestrator.active == "Concierge"

        # Update with new scenario where Concierge exists
        new_agents = {
            "Concierge": FakeVoiceLiveAgent("Concierge"),
            "Banking": FakeVoiceLiveAgent("Banking"),
        }
        orchestrator.update_scenario(
            agents=new_agents,
            handoff_map={},
            start_agent=None,  # No explicit start agent
        )

        # Should still be Concierge
        assert orchestrator.active == "Concierge"

        orchestrator.cleanup()

    def test_update_scenario_updates_handoff_map(self):
        """Verify update_scenario correctly updates handoff map."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={"Concierge": "Support"},
            start_agent="Concierge",
        )

        assert orchestrator._handoff_map == {"Concierge": "Support"}

        # Update with new handoff map
        new_agents = {"Banking": FakeVoiceLiveAgent("Banking")}
        orchestrator.update_scenario(
            agents=new_agents,
            handoff_map={"Banking": "Investments"},
            start_agent="Banking",
        )

        assert orchestrator._handoff_map == {"Banking": "Investments"}

        orchestrator.cleanup()

    def test_update_scenario_clears_visited_agents(self):
        """Verify update_scenario clears visited_agents for fresh experience."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Simulate visiting some agents
        orchestrator.visited_agents.add("Concierge")
        orchestrator.visited_agents.add("Banking")
        assert len(orchestrator.visited_agents) == 2

        # Update with new scenario
        new_agents = {"InvestmentAdvisor": FakeVoiceLiveAgent("InvestmentAdvisor")}
        orchestrator.update_scenario(
            agents=new_agents,
            handoff_map={},
            start_agent="InvestmentAdvisor",
        )

        # visited_agents should be cleared
        assert len(orchestrator.visited_agents) == 0

        orchestrator.cleanup()

    def test_update_scenario_always_switches_to_start_agent(self):
        """Verify update_scenario always switches to start_agent when provided."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {
            "Concierge": FakeVoiceLiveAgent("Concierge"),
            "Banking": FakeVoiceLiveAgent("Banking"),
        }

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        assert orchestrator.active == "Concierge"

        # Update with same agents but different start_agent
        # This should switch even though Concierge exists in new scenario
        orchestrator.update_scenario(
            agents=agents,
            handoff_map={},
            start_agent="Banking",
        )

        # Should have switched to Banking
        assert orchestrator.active == "Banking"

        orchestrator.cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# HOT PATH OPTIMIZATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHotPathOptimization:
    """Tests for hot path latency optimization."""

    @pytest.mark.asyncio
    async def test_schedule_throttled_session_update_is_non_blocking(self):
        """Verify _schedule_throttled_session_update doesn't block."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Reset the last update time to force an update
        orchestrator._last_session_update_time = 0
        orchestrator._pending_session_update = True

        # Should not raise and should return immediately
        # (the actual network call is scheduled as background task)
        orchestrator._schedule_throttled_session_update()

        # Allow any scheduled tasks to run
        await asyncio.sleep(0.01)

        orchestrator.cleanup()

    def test_schedule_throttled_session_update_throttles_correctly(self):
        """Verify throttling prevents too-frequent updates."""
        import time
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Set recent update time
        orchestrator._last_session_update_time = time.perf_counter()
        orchestrator._pending_session_update = False

        initial_time = orchestrator._last_session_update_time

        # Call should be throttled (skipped)
        orchestrator._schedule_throttled_session_update()

        # Time should not be updated since it was throttled
        assert orchestrator._last_session_update_time == initial_time

        orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_schedule_throttled_session_update_respects_pending_flag(self):
        """Verify pending flag bypasses throttle."""
        import time
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Set recent update time but also pending flag
        orchestrator._last_session_update_time = time.perf_counter()
        orchestrator._pending_session_update = True

        initial_time = orchestrator._last_session_update_time

        # Call should NOT be throttled due to pending flag
        orchestrator._schedule_throttled_session_update()

        # Allow any scheduled tasks to run
        await asyncio.sleep(0.01)

        # Time should be updated (update was scheduled)
        assert orchestrator._last_session_update_time > initial_time
        # Pending flag should be cleared
        assert orchestrator._pending_session_update is False

        orchestrator.cleanup()

    def test_schedule_background_sync_is_non_blocking(self):
        """Verify _schedule_background_sync doesn't block."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}
        memo_manager = MagicMock()

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
            memo_manager=memo_manager,
        )

        # Should not raise and should return immediately
        orchestrator._schedule_background_sync()

        orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_handle_response_done_is_non_blocking(self):
        """Verify _handle_response_done doesn't block on network calls."""
        import time
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Create a mock event
        event = MagicMock()
        event.response = MagicMock()
        event.response.id = "test-response-id"
        event.usage = None

        # Measure execution time
        start = time.perf_counter()
        await orchestrator._handle_response_done(event)
        elapsed = time.perf_counter() - start

        # Should complete very quickly (< 100ms) since network calls are backgrounded
        assert elapsed < 0.1, f"_handle_response_done took {elapsed*1000:.1f}ms, expected < 100ms"

        orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_handle_speech_started_uses_background_sync(self):
        """Verify _handle_speech_started uses background sync instead of blocking."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}
        memo_manager = MagicMock()

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
            memo_manager=memo_manager,
        )

        # Patch _schedule_background_sync to verify it's called
        with patch.object(orchestrator, "_schedule_background_sync") as mock_sync:
            await orchestrator._handle_speech_started()
            mock_sync.assert_called_once()

        orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_handle_transcription_completed_sets_pending_flag(self):
        """Verify transcription completed sets pending flag instead of blocking."""
        from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator

        conn = FakeVoiceLiveConnection()
        agents = {"Concierge": FakeVoiceLiveAgent("Concierge")}

        orchestrator = LiveOrchestrator(
            conn=conn,
            agents=agents,
            handoff_map={},
            start_agent="Concierge",
        )

        # Initially no pending update
        orchestrator._pending_session_update = False

        # Create mock event
        event = MagicMock()
        event.transcript = "test transcript"
        event.item = MagicMock()
        event.item.id = "test-item-id"

        await orchestrator._handle_transcription_completed(event)

        # Should have set pending flag
        assert orchestrator._pending_session_update is True

        orchestrator.cleanup()

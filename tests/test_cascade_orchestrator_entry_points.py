"""
Cascade Orchestrator Entry Point Regression Tests
==================================================

These tests capture the current behavior of the CascadeOrchestratorAdapter
entry point methods BEFORE Priority 1 refactoring.

Priority 1 Refactoring Goals:
- Remove as_orchestrator_func() wrapper
- Consolidate process_user_input() into process_turn()
- Remove factory function wrappers (get_cascade_orchestrator, create_cascade_orchestrator_func)
- Make process_turn() the single entry point

These tests ensure we don't break functionality during refactoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

if TYPE_CHECKING:
    from apps.artagent.backend.voice.shared.base import OrchestratorContext

# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_memo_manager():
    """Create a mock MemoManager for testing."""
    mm = MagicMock()
    mm.get_history = MagicMock(return_value=[])
    mm.append_to_history = MagicMock()
    mm.get_value_from_corememory = MagicMock(return_value=None)
    mm.history.get_all = MagicMock(return_value={})
    return mm


@pytest.fixture
def mock_agent():
    """Create a mock UnifiedAgent."""
    from apps.artagent.backend.registries.agentstore.base import ModelConfig, UnifiedAgent

    return UnifiedAgent(
        name="TestAgent",
        description="Test agent for entry point tests",
        greeting="Hello, I'm TestAgent",
        model=ModelConfig(deployment_id="gpt-4o", temperature=0.7),
        prompt_template="You are a test agent.",
        tool_names=[],
    )


@pytest.fixture
def cascade_adapter(mock_agent):
    """Create a CascadeOrchestratorAdapter with mock agent."""
    from apps.artagent.backend.voice.speech_cascade.orchestrator import (
        CascadeConfig,
        CascadeOrchestratorAdapter,
    )

    config = CascadeConfig(
        start_agent="TestAgent",
        session_id="test-session",
        call_connection_id="test-call",
    )

    adapter = CascadeOrchestratorAdapter(
        config=config,
        agents={"TestAgent": mock_agent},
        handoff_map={},
    )

    return adapter


# ═══════════════════════════════════════════════════════════════════════════════
# BASELINE TESTS - Entry Point Wrappers
# ═══════════════════════════════════════════════════════════════════════════════


class TestEntryPointWrappers:
    """
    BASELINE: Test current entry point wrapper behavior.

    These test the 4-layer entry point nesting:
    - Factory functions (get_cascade_orchestrator, create_cascade_orchestrator_func)
    - as_orchestrator_func()
    - process_user_input()
    - process_turn()

    After Priority 1 refactoring, these tests should be replaced with
    simpler tests for the unified process_turn() entry point.
    """

    @pytest.mark.asyncio
    async def test_process_turn_is_core_entry_point(
        self, cascade_adapter, mock_memo_manager
    ):
        """
        BASELINE: process_turn() should be the core orchestration method.

        This test verifies that process_turn() accepts OrchestratorContext
        and returns OrchestratorResult. This should remain after refactoring.
        """
        from apps.artagent.backend.voice.shared.base import OrchestratorContext

        context = OrchestratorContext(
            session_id="test-session",
            user_text="Hello",
            conversation_history=[],
            metadata={"memo_manager": mock_memo_manager},
        )

        # Mock LLM processing to avoid actual API calls
        with patch.object(
            cascade_adapter, "_process_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = ("Test response", [])

            result = await cascade_adapter.process_turn(context)

            # Verify result structure
            assert hasattr(result, "response_text")
            assert hasattr(result, "agent_name")
            assert result.agent_name == "TestAgent"

    @pytest.mark.asyncio
    async def test_process_user_input_wraps_process_turn(
        self, cascade_adapter, mock_memo_manager
    ):
        """
        BASELINE: process_user_input() should wrap process_turn().

        After refactoring, this wrapper should be removed and callers should
        use process_turn() directly.
        """
        # Mock LLM processing
        with patch.object(
            cascade_adapter, "_process_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = ("Test response", [])

            # Call process_user_input (wrapper)
            response = await cascade_adapter.process_user_input(
                transcript="Hello", cm=mock_memo_manager
            )

            # Verify it returns text response
            assert response == "Test response"

            # Verify history was updated
            assert mock_memo_manager.append_to_history.called

    @pytest.mark.asyncio
    async def test_as_orchestrator_func_returns_callable(self, cascade_adapter):
        """
        BASELINE: as_orchestrator_func() should return a callable.

        After refactoring, this wrapper should be removed. Callers should
        instantiate the adapter and use process_turn() directly.
        """
        orchestrator_func = cascade_adapter.as_orchestrator_func()

        # Verify it returns a callable
        assert callable(orchestrator_func)

        # Verify the signature matches expected interface
        import inspect

        sig = inspect.signature(orchestrator_func)
        params = list(sig.parameters.keys())
        assert "cm" in params
        assert "transcript" in params

    def test_factory_create_returns_adapter(self):
        """
        BASELINE: CascadeOrchestratorAdapter.create() should return configured adapter.

        After refactoring, .create() factory should remain but factory functions
        (get_cascade_orchestrator, create_cascade_orchestrator_func) should be removed.
        """
        from apps.artagent.backend.voice.speech_cascade.orchestrator import (
            CascadeOrchestratorAdapter,
        )

        adapter = CascadeOrchestratorAdapter.create(
            start_agent="TestAgent", session_id="test-session"
        )

        # Verify adapter configuration
        assert adapter.config.start_agent == "TestAgent"
        assert adapter.config.session_id == "test-session"
        assert isinstance(adapter, CascadeOrchestratorAdapter)


# ═══════════════════════════════════════════════════════════════════════════════
# BASELINE TESTS - Context Building
# ═══════════════════════════════════════════════════════════════════════════════


class TestContextBuilding:
    """
    BASELINE: Test context building behavior.

    Tests verify that _build_session_context() produces correct dict.
    After refactoring, this should be the ONLY context building method
    (currently duplicated in process_user_input).
    """

    def test_build_session_context_returns_dict(
        self, cascade_adapter, mock_memo_manager
    ):
        """
        BASELINE: _build_session_context() should return dict with session vars.

        This should remain after refactoring as the single source of session context.
        """
        context = cascade_adapter._build_session_context(mock_memo_manager)

        # Verify required keys
        assert "memo_manager" in context
        assert "session_profile" in context
        assert "caller_name" in context
        assert "client_id" in context
        assert context["memo_manager"] is mock_memo_manager

    def test_context_building_not_duplicated(self):
        """
        SUCCESS: Context building is no longer duplicated after refactoring!

        Before refactoring: context building was duplicated in process_user_input().
        After refactoring: process_user_input() is now a thin shim that calls process_turn().
        """
        import inspect

        from apps.artagent.backend.voice.speech_cascade.orchestrator import (
            CascadeOrchestratorAdapter,
        )

        # Get source of process_user_input
        source = inspect.getsource(CascadeOrchestratorAdapter.process_user_input)

        # After refactoring: process_user_input should be a thin shim (no duplication)
        assert "session_profile" not in source  # No longer duplicated!
        assert "process_turn" in source  # Should delegate to process_turn()
        assert "DEPRECATED" in source  # Should be marked deprecated


# ═══════════════════════════════════════════════════════════════════════════════
# BASELINE TESTS - History Management
# ═══════════════════════════════════════════════════════════════════════════════


class TestHistoryManagement:
    """
    BASELINE: Test history management behavior.

    Tests verify that history operations work correctly.
    After refactoring, history should be managed in fewer, clearer methods.
    """

    def test_get_conversation_history(self, cascade_adapter, mock_memo_manager):
        """
        BASELINE: _get_conversation_history() should return history list.

        This should remain but be simplified to not duplicate history operations.
        """
        mock_memo_manager.get_history.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        history = cascade_adapter._get_conversation_history(mock_memo_manager)

        # Should return the history
        assert isinstance(history, list)
        assert len(history) >= 2

    def test_record_turn(self, cascade_adapter, mock_memo_manager):
        """
        BASELINE: _record_turn() should append messages to history.

        This should remain as the single place to record history.
        """
        cascade_adapter._current_memo_manager = mock_memo_manager

        user_recorded, assistant_recorded = cascade_adapter._record_turn(
            agent="TestAgent", user_text="Hello", assistant_text="Hi"
        )

        # Verify both messages recorded
        assert user_recorded is True
        assert assistant_recorded is True
        assert mock_memo_manager.append_to_history.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# POST-REFACTORING TARGET TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestPostRefactoringTargets:
    """
    TARGET: Tests for desired post-refactoring behavior.

    These tests should PASS after Priority 1 refactoring.
    They may currently FAIL because the code hasn't been refactored yet.
    """

    @pytest.mark.skip(reason="Target for post-refactoring - currently fails")
    def test_single_entry_point_process_turn_with_memo_manager(self):
        """
        TARGET: After refactoring, process_turn() should accept MemoManager directly.

        Currently, process_user_input() wraps process_turn() to handle MemoManager.
        After refactoring, process_turn() should handle it directly.
        """
        # This is how it SHOULD work after refactoring
        from apps.artagent.backend.voice.speech_cascade.orchestrator import (
            CascadeOrchestratorAdapter,
        )

        adapter = CascadeOrchestratorAdapter.create(start_agent="TestAgent")

        # Should be able to pass MemoManager directly to process_turn
        # Currently requires wrapping with process_user_input
        # After refactoring: process_turn signature should support this
        pass

    @pytest.mark.skip(reason="Target for post-refactoring - currently fails")
    def test_no_wrapper_functions_exist(self):
        """
        TARGET: After refactoring, wrapper functions should not exist.

        These should be removed:
        - get_cascade_orchestrator()
        - create_cascade_orchestrator_func()
        - as_orchestrator_func()
        - process_user_input() (consolidated into process_turn)
        """
        from apps.artagent.backend.voice.speech_cascade import orchestrator

        # After refactoring, these should not exist
        assert not hasattr(orchestrator, "get_cascade_orchestrator")
        assert not hasattr(orchestrator, "create_cascade_orchestrator_func")
        assert not hasattr(
            orchestrator.CascadeOrchestratorAdapter, "as_orchestrator_func"
        )
        assert not hasattr(
            orchestrator.CascadeOrchestratorAdapter, "process_user_input"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION SMOKE TEST
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationSmokeTest:
    """
    SMOKE TEST: End-to-end integration test.

    This test should pass both before and after refactoring.
    """

    @pytest.mark.asyncio
    async def test_end_to_end_process_turn(self, mock_agent, mock_memo_manager):
        """
        SMOKE TEST: Full process_turn flow should work.

        This test should pass before AND after refactoring.
        """
        from apps.artagent.backend.voice.shared.base import OrchestratorContext
        from apps.artagent.backend.voice.speech_cascade.orchestrator import (
            CascadeConfig,
            CascadeOrchestratorAdapter,
        )

        # Create adapter
        config = CascadeConfig(
            start_agent="TestAgent",
            session_id="smoke-test-session",
            call_connection_id="smoke-test-call",
        )

        adapter = CascadeOrchestratorAdapter(
            config=config, agents={"TestAgent": mock_agent}, handoff_map={}
        )

        # Mock LLM call
        with patch.object(
            adapter, "_process_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = ("Smoke test response", [])

            # Create context
            context = OrchestratorContext(
                session_id="smoke-test-session",
                user_text="Test query",
                conversation_history=[],
                metadata={"memo_manager": mock_memo_manager},
            )

            # Process turn
            result = await adapter.process_turn(context)

            # Verify result
            assert result.response_text == "Smoke test response"
            assert result.agent_name == "TestAgent"
            assert result.error is None
            assert result.interrupted is False

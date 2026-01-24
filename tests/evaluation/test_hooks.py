"""
Tests for evaluation hooks.

Validates:
- Hook interfaces work correctly
- Built-in hooks use correct TurnEvent fields
- Hooks handle edge cases gracefully
"""

import pytest
from unittest.mock import MagicMock

from tests.evaluation.schemas import (
    EvalModelConfig,
    HandoffEvent,
    TurnEvent,
    ToolCall,
)
from tests.evaluation.hooks import (
    HookResult,
    TurnHook,
    ToolHook,
    PreScoreHook,
    HookRegistry,
    LogMetricsHook,
    ValidateExpectationsHook,
    CaptureReasoningHook,
)
from tests.evaluation.hooks.builtin import (
    ToolResultValidatorHook,
    AggregateMetricsHook,
)


# =============================================================================
# Fixtures
# =============================================================================


def make_model_config(**kwargs) -> EvalModelConfig:
    """Create a test model config."""
    defaults = {
        "model_name": "gpt-4o",
        "endpoint_used": "chat",
    }
    defaults.update(kwargs)
    return EvalModelConfig(**defaults)


def make_turn(
    turn_id: str = "test_turn_1",
    user_text: str = "Hello",
    response_text: str = "Hi there!",
    e2e_ms: float = 500.0,
    **kwargs,
) -> TurnEvent:
    """Create a test TurnEvent."""
    defaults = {
        "session_id": "test_session",
        "turn_id": turn_id,
        "user_end_ts": 1000.0,
        "agent_last_output_ts": 1500.0,
        "e2e_ms": e2e_ms,
        "agent_name": "TestAgent",
        "user_text": user_text,
        "response_text": response_text,
        "eval_model_config": make_model_config(),
    }
    defaults.update(kwargs)
    return TurnEvent(**defaults)


def make_tool_call(name: str = "test_tool", **kwargs) -> ToolCall:
    """Create a test ToolCall."""
    defaults = {
        "name": name,
        "arguments": {},
        "start_ts": 1000.0,
        "end_ts": 1100.0,
        "duration_ms": 100.0,
        "status": "success",
        "result_hash": "abc123",
    }
    defaults.update(kwargs)
    return ToolCall(**defaults)


def make_handoff(source: str = "AgentA", target: str = "AgentB") -> HandoffEvent:
    """Create a test HandoffEvent."""
    return HandoffEvent(
        source_agent=source,
        target_agent=target,
        timestamp=1000.0,
    )


# =============================================================================
# HookResult Tests
# =============================================================================


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_empty_result(self):
        """Empty result has empty fields."""
        result = HookResult()
        assert result.metadata == {}
        assert result.warnings == []

    def test_result_with_metadata(self):
        """Result can store metadata."""
        result = HookResult(metadata={"key": "value"})
        assert result.metadata == {"key": "value"}

    def test_result_with_warnings(self):
        """Result can store warnings."""
        result = HookResult(warnings=["warning1", "warning2"])
        assert len(result.warnings) == 2

    def test_merge_results(self):
        """Two results can be merged."""
        r1 = HookResult(metadata={"a": 1}, warnings=["w1"])
        r2 = HookResult(metadata={"b": 2}, warnings=["w2"])

        merged = r1.merge(r2)

        assert merged.metadata == {"a": 1, "b": 2}
        assert merged.warnings == ["w1", "w2"]


# =============================================================================
# LogMetricsHook Tests
# =============================================================================


class TestLogMetricsHook:
    """Tests for LogMetricsHook."""

    @pytest.mark.asyncio
    async def test_basic_turn_logging(self):
        """Hook logs basic turn info."""
        hook = LogMetricsHook()
        turn = make_turn()

        result = await hook.on_turn_complete(turn, {})

        assert isinstance(result, HookResult)
        # Hook doesn't add metadata, just logs
        assert result.metadata == {}
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_with_tool_calls(self):
        """Hook handles turns with tool calls."""
        hook = LogMetricsHook()
        turn = make_turn(
            tool_calls=[
                make_tool_call("tool_a"),
                make_tool_call("tool_b"),
            ]
        )

        result = await hook.on_turn_complete(turn, {})

        # Should complete without error
        assert isinstance(result, HookResult)

    @pytest.mark.asyncio
    async def test_with_handoff(self):
        """Hook handles turns with handoffs using correct field name."""
        hook = LogMetricsHook()
        turn = make_turn(handoff=make_handoff("Concierge", "FraudAgent"))

        result = await hook.on_turn_complete(turn, {})

        # Should complete without error (uses turn.handoff.target_agent)
        assert isinstance(result, HookResult)

    @pytest.mark.asyncio
    async def test_uses_e2e_ms_field(self):
        """Hook uses e2e_ms (not e2e_latency_ms)."""
        hook = LogMetricsHook()
        turn = make_turn(e2e_ms=1234.5)

        # Should not raise AttributeError
        result = await hook.on_turn_complete(turn, {})
        assert isinstance(result, HookResult)


# =============================================================================
# CaptureReasoningHook Tests
# =============================================================================


class TestCaptureReasoningHook:
    """Tests for CaptureReasoningHook."""

    @pytest.mark.asyncio
    async def test_no_reasoning_tokens(self):
        """Hook returns empty result when no reasoning tokens."""
        hook = CaptureReasoningHook()
        turn = make_turn()

        result = await hook.on_turn_complete(turn, {})

        assert result.metadata == {}

    @pytest.mark.asyncio
    async def test_with_reasoning_tokens(self):
        """Hook captures reasoning tokens correctly."""
        hook = CaptureReasoningHook()
        turn = make_turn(
            reasoning_tokens=500,
            eval_model_config=make_model_config(
                model_name="o3-mini",
                include_reasoning=True,
            ),
        )

        result = await hook.on_turn_complete(turn, {})

        assert "reasoning" in result.metadata
        assert result.metadata["reasoning"]["tokens"] == 500
        assert result.metadata["reasoning"]["include_reasoning"] is True

    @pytest.mark.asyncio
    async def test_with_reasoning_effort(self):
        """Hook captures reasoning effort setting."""
        hook = CaptureReasoningHook()
        turn = make_turn(
            eval_model_config=make_model_config(
                model_name="o3-mini",
                reasoning_effort="high",
            ),
        )

        result = await hook.on_turn_complete(turn, {})

        assert "reasoning" in result.metadata
        assert result.metadata["reasoning"]["effort"] == "high"


# =============================================================================
# ToolResultValidatorHook Tests
# =============================================================================


class TestToolResultValidatorHook:
    """Tests for ToolResultValidatorHook."""

    @pytest.mark.asyncio
    async def test_valid_result(self):
        """Hook accepts valid results."""
        hook = ToolResultValidatorHook()

        result = await hook.on_tool_complete(
            "test_tool",
            {"status": "success", "data": [1, 2, 3]},
            {},
        )

        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_none_result_warning(self):
        """Hook warns on None result."""
        hook = ToolResultValidatorHook()

        result = await hook.on_tool_complete("test_tool", None, {})

        assert len(result.warnings) == 1
        assert "None" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_empty_dict_warning(self):
        """Hook warns on empty dict result."""
        hook = ToolResultValidatorHook()

        result = await hook.on_tool_complete("test_tool", {}, {})

        assert len(result.warnings) == 1
        assert "empty dict" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_error_in_result_warning(self):
        """Hook warns when result contains error."""
        hook = ToolResultValidatorHook()

        result = await hook.on_tool_complete(
            "test_tool",
            {"error": "Something went wrong"},
            {},
        )

        assert len(result.warnings) == 1
        assert "error" in result.warnings[0].lower()


# =============================================================================
# AggregateMetricsHook Tests
# =============================================================================


class TestAggregateMetricsHook:
    """Tests for AggregateMetricsHook."""

    @pytest.mark.asyncio
    async def test_empty_events(self):
        """Hook handles empty events list."""
        hook = AggregateMetricsHook()

        result = await hook.pre_score([], {})

        assert "aggregate" in result.metadata
        assert result.metadata["aggregate"]["total_tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_counts_tools(self):
        """Hook counts total tool calls."""
        hook = AggregateMetricsHook()
        events = [
            make_turn(tool_calls=[make_tool_call("tool_a"), make_tool_call("tool_b")]),
            make_turn(tool_calls=[make_tool_call("tool_a")]),
        ]

        result = await hook.pre_score(events, {})

        assert result.metadata["aggregate"]["total_tool_calls"] == 3
        assert result.metadata["aggregate"]["unique_tool_count"] == 2

    @pytest.mark.asyncio
    async def test_tracks_agents(self):
        """Hook tracks agents used."""
        hook = AggregateMetricsHook()
        events = [
            make_turn(agent_name="AgentA"),
            make_turn(agent_name="AgentB"),
            make_turn(agent_name="AgentA"),
        ]

        result = await hook.pre_score(events, {})

        assert len(result.metadata["aggregate"]["agents_used"]) == 2

    @pytest.mark.asyncio
    async def test_tracks_handoff_chain_with_correct_field(self):
        """Hook tracks handoffs using target_agent field."""
        hook = AggregateMetricsHook()
        events = [
            make_turn(
                agent_name="Concierge",
                handoff=make_handoff("Concierge", "FraudAgent"),
            ),
            make_turn(agent_name="FraudAgent"),
        ]

        result = await hook.pre_score(events, {})

        handoff_chain = result.metadata["aggregate"]["handoff_chain"]
        assert len(handoff_chain) == 1
        assert "Concierge->FraudAgent" in handoff_chain[0]


# =============================================================================
# HookRegistry Tests
# =============================================================================


class TestHookRegistry:
    """Tests for HookRegistry."""

    def test_registry_creation(self):
        """Registry can be created."""
        registry = HookRegistry()
        assert registry is not None

    def test_register_turn_hook(self):
        """Can register a turn hook programmatically."""
        registry = HookRegistry()
        hook = LogMetricsHook()

        registry.register_turn_hook(hook)

        assert registry.has_turn_hooks

    def test_load_from_config_builtin(self):
        """Can load built-in hooks from config."""
        registry = HookRegistry()
        registry.load_from_config({
            "on_turn_complete": ["builtin.log_metrics"],
        })

        assert registry.has_turn_hooks

    @pytest.mark.asyncio
    async def test_dispatch_turn_complete(self):
        """Can dispatch to registered turn hooks."""
        registry = HookRegistry()
        registry.register_turn_hook(LogMetricsHook())

        turn = make_turn()
        result = await registry.dispatch_turn_complete(turn, {})

        assert isinstance(result, HookResult)

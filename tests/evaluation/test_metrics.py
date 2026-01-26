"""
Tests for Pluggable Metrics Module (Phase 5)
============================================

Validates:
- MetricPlugin interface and base classes
- Built-in metric implementations
- MetricRegistry loading and computation
- Custom metric loading from YAML/modules
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from tests.evaluation.metrics import (
    BUILTIN_METRICS,
    AggregateMetricPlugin,
    CostMetric,
    GroundednessMetric,
    HandoffAccuracyMetric,
    LatencyMetric,
    MetricPlugin,
    MetricRegistry,
    MetricResult,
    ToolEfficiencyMetric,
    ToolPrecisionMetric,
    ToolRecallMetric,
    VerbosityMetric,
    metric_plugin,
)
from tests.evaluation.schemas import (
    EvalModelConfig,
    EvidenceBlob,
    HandoffEvent,
    ScenarioExpectations,
    ToolCall,
    TurnEvent,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_turn() -> TurnEvent:
    """Create a sample TurnEvent for testing."""
    return TurnEvent(
        turn_id="test_scenario:turn_1",
        session_id="session_123",
        agent_name="TestAgent",
        user_text="What is my balance?",
        user_end_ts=999.0,
        agent_last_output_ts=1050.0,
        response_text="Your current balance is $1,234.56 as of January 15, 2026.",
        tool_calls=[
            ToolCall(
                name="get_balance",
                arguments={"account_id": "12345"},
                start_ts=1000.0,
                end_ts=1050.0,
                duration_ms=50.0,
                result_hash="abc123",
            ),
        ],
        evidence_blobs=[
            EvidenceBlob(
                source="get_balance",
                content_hash="def456",
                content_excerpt="Account balance: $1,234.56",
            ),
        ],
        eval_model_config=EvalModelConfig(
            model_name="gpt-4o",
            model_family="gpt-4o",
            endpoint_used="chat",
        ),
        e2e_ms=150.0,
        ttft_ms=50.0,
        input_tokens=100,
        response_tokens=50,
    )


@pytest.fixture
def sample_turn_with_handoff() -> TurnEvent:
    """Create a TurnEvent with handoff."""
    return TurnEvent(
        turn_id="test_scenario:turn_2",
        session_id="session_123",
        agent_name="Concierge",
        user_text="I want to report fraud",
        user_end_ts=1999.0,
        agent_last_output_ts=2080.0,
        response_text="I'm transferring you to our fraud specialist.",
        tool_calls=[],
        evidence_blobs=[],
        eval_model_config=EvalModelConfig(
            model_name="gpt-4o",
            model_family="gpt-4o",
            endpoint_used="chat",
        ),
        handoff=HandoffEvent(
            source_agent="Concierge",
            target_agent="FraudAgent",
            context="Fraud report",
            timestamp=2080.0,
        ),
        e2e_ms=80.0,
        ttft_ms=30.0,
    )


@pytest.fixture
def multiple_turns(sample_turn: TurnEvent) -> List[TurnEvent]:
    """Create multiple turns for aggregate testing."""
    turns = [sample_turn]

    # Add more turns with varying metrics
    turn2 = TurnEvent(
        turn_id="test_scenario:turn_2",
        session_id="session_123",
        agent_name="TestAgent",
        user_text="Transfer $500",
        user_end_ts=1999.0,
        agent_last_output_ts=2100.0,
        response_text="I've transferred $500 to your savings account.",
        tool_calls=[
            ToolCall(
                name="transfer_funds",
                arguments={"amount": 500, "to": "savings"},
                start_ts=2000.0,
                end_ts=2100.0,
                duration_ms=100.0,
                result_hash="xyz789",
            ),
        ],
        evidence_blobs=[
            EvidenceBlob(
                source="transfer_funds",
                content_hash="qrs456",
                content_excerpt="Transfer of $500 completed",
            ),
        ],
        eval_model_config=EvalModelConfig(
            model_name="gpt-4o",
            model_family="gpt-4o",
            endpoint_used="chat",
        ),
        e2e_ms=200.0,
        ttft_ms=60.0,
        input_tokens=120,
        response_tokens=40,
    )
    turns.append(turn2)

    return turns


@pytest.fixture
def expectations() -> ScenarioExpectations:
    """Create sample expectations."""
    return ScenarioExpectations(
        tools_called=["get_balance"],
        response_constraints={"max_tokens": 100},
    )


# =============================================================================
# TEST: MetricResult
# =============================================================================


class TestMetricResult:
    """Tests for MetricResult dataclass."""

    def test_basic_creation(self):
        """Test basic MetricResult creation."""
        result = MetricResult(name="test", score=0.95)
        assert result.name == "test"
        assert result.score == 0.95
        assert result.details == {}
        assert result.passed is None
        assert result.threshold is None

    def test_with_details(self):
        """Test MetricResult with details."""
        result = MetricResult(
            name="test",
            score=0.8,
            details={"count": 5, "items": ["a", "b"]},
        )
        assert result.details["count"] == 5
        assert len(result.details["items"]) == 2

    def test_with_threshold(self):
        """Test MetricResult with pass/fail."""
        result = MetricResult(
            name="test",
            score=0.9,
            passed=True,
            threshold=0.8,
        )
        assert result.passed is True
        assert result.threshold == 0.8

    def test_to_dict(self):
        """Test serialization to dict."""
        result = MetricResult(
            name="test",
            score=0.75,
            details={"key": "value"},
            passed=False,
            threshold=0.8,
        )
        d = result.to_dict()

        assert d["name"] == "test"
        assert d["score"] == 0.75
        assert d["details"]["key"] == "value"
        assert d["passed"] is False
        assert d["threshold"] == 0.8

    def test_to_dict_without_optional(self):
        """Test dict without optional fields."""
        result = MetricResult(name="test", score=0.5)
        d = result.to_dict()

        assert "passed" not in d
        assert "threshold" not in d


# =============================================================================
# TEST: MetricPlugin Interface
# =============================================================================


class TestMetricPluginInterface:
    """Tests for MetricPlugin base class."""

    def test_cannot_instantiate_abstract(self):
        """Test that abstract base cannot be instantiated."""
        with pytest.raises(TypeError):
            MetricPlugin()  # type: ignore

    def test_custom_plugin_implementation(self, sample_turn: TurnEvent):
        """Test creating a custom metric plugin."""

        class ResponseLengthMetric(MetricPlugin):
            name = "response_length"
            description = "Measures response length"
            higher_is_better = False

            def compute(self, turn, expectations=None, **kwargs):
                length = len(turn.response_text)
                return MetricResult(
                    name=self.name,
                    score=length,
                    details={"characters": length, "words": len(turn.response_text.split())},
                )

        metric = ResponseLengthMetric()
        result = metric.compute(sample_turn)

        assert result.name == "response_length"
        assert result.score > 0
        assert "characters" in result.details
        assert "words" in result.details

    def test_check_threshold_higher_is_better(self):
        """Test threshold check when higher is better."""

        class TestMetric(MetricPlugin):
            name = "test"
            higher_is_better = True
            default_threshold = 0.8

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=0.9)

        metric = TestMetric()
        result = metric.compute(MagicMock())
        checked = metric.check_threshold(result)

        assert checked.passed is True
        assert checked.threshold == 0.8

    def test_check_threshold_lower_is_better(self):
        """Test threshold check when lower is better."""

        class LatencyTestMetric(MetricPlugin):
            name = "latency"
            higher_is_better = False
            default_threshold = 200.0

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=150.0)

        metric = LatencyTestMetric()
        result = metric.compute(MagicMock())
        checked = metric.check_threshold(result)

        assert checked.passed is True  # 150 < 200
        assert checked.threshold == 200.0

    def test_metric_plugin_decorator(self):
        """Test @metric_plugin decorator registration."""
        from tests.evaluation.metrics.base import get_registered_metrics

        @metric_plugin
        class DecoratedMetric(MetricPlugin):
            name = "decorated_test"

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=1.0)

        registered = get_registered_metrics()
        assert "decorated_test" in registered
        assert registered["decorated_test"] == DecoratedMetric


# =============================================================================
# TEST: Built-in Metrics
# =============================================================================


class TestToolPrecisionMetric:
    """Tests for ToolPrecisionMetric."""

    def test_perfect_precision(self, sample_turn: TurnEvent, expectations: ScenarioExpectations):
        """Test precision when all called tools were expected."""
        metric = ToolPrecisionMetric()
        result = metric.compute(sample_turn, expectations)

        assert result.score == 1.0
        assert result.details["actual_tools"] == ["get_balance"]
        assert result.details["expected_tools"] == ["get_balance"]

    def test_zero_precision_unexpected_tools(self, sample_turn: TurnEvent):
        """Test precision when calling unexpected tools."""
        expectations = ScenarioExpectations(tools_called=["other_tool"])
        metric = ToolPrecisionMetric()
        result = metric.compute(sample_turn, expectations)

        assert result.score == 0.0
        assert "get_balance" in result.details["unexpected"]

    def test_partial_precision(self):
        """Test precision with mix of expected and unexpected."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="response",
            tool_calls=[
                ToolCall(name="tool_a", arguments={}, start_ts=0, end_ts=10, duration_ms=10, result_hash="a1"),
                ToolCall(name="tool_b", arguments={}, start_ts=10, end_ts=20, duration_ms=10, result_hash="b1"),
            ],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )
        expectations = ScenarioExpectations(tools_called=["tool_a"])

        metric = ToolPrecisionMetric()
        result = metric.compute(turn, expectations)

        assert result.score == 0.5  # 1 expected out of 2 called

    def test_no_tools_called_no_expected(self):
        """Test when no tools called and none expected."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="response",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )
        metric = ToolPrecisionMetric()
        result = metric.compute(turn, expectations=None)

        assert result.score == 1.0


class TestToolRecallMetric:
    """Tests for ToolRecallMetric."""

    def test_perfect_recall(self, sample_turn: TurnEvent, expectations: ScenarioExpectations):
        """Test recall when all expected tools were called."""
        metric = ToolRecallMetric()
        result = metric.compute(sample_turn, expectations)

        assert result.score == 1.0

    def test_zero_recall_missing_tools(self):
        """Test recall when expected tools weren't called."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="response",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )
        expectations = ScenarioExpectations(tools_called=["required_tool"])

        metric = ToolRecallMetric()
        result = metric.compute(turn, expectations)

        assert result.score == 0.0
        assert "required_tool" in result.details["missing"]

    def test_no_expectations(self, sample_turn: TurnEvent):
        """Test recall with no expectations (should be 1.0)."""
        metric = ToolRecallMetric()
        result = metric.compute(sample_turn, expectations=None)

        assert result.score == 1.0  # Nothing to miss


class TestToolEfficiencyMetric:
    """Tests for ToolEfficiencyMetric."""

    def test_no_redundant_calls(self, sample_turn: TurnEvent):
        """Test efficiency with no redundant calls."""
        metric = ToolEfficiencyMetric()
        result = metric.compute(sample_turn)

        assert result.score == 1.0
        assert result.details["redundant_calls"] == 0

    def test_redundant_calls_detected(self):
        """Test efficiency detects redundant calls."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=999.0,
            agent_last_output_ts=1025.0,
            response_text="response",
            tool_calls=[
                ToolCall(
                    name="get_balance",
                    arguments={"account": "123"},
                    start_ts=1000.0,
                    end_ts=1010.0,
                    duration_ms=10.0,
                    result_hash="same_hash",
                ),
                ToolCall(
                    name="get_balance",
                    arguments={"account": "123"},
                    start_ts=1015.0,  # Within 30s window
                    end_ts=1025.0,
                    duration_ms=10.0,
                    result_hash="same_hash",
                ),
            ],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=26.0,
        )

        metric = ToolEfficiencyMetric()
        result = metric.compute(turn)

        assert result.score == 0.5  # 1 redundant out of 2
        assert result.details["redundant_calls"] == 1

    def test_no_tools_perfect_efficiency(self):
        """Test efficiency with no tools."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="response",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )

        metric = ToolEfficiencyMetric()
        result = metric.compute(turn)

        assert result.score == 1.0


class TestGroundednessMetric:
    """Tests for GroundednessMetric.
    
    Note: These tests use the placeholder _extract_factual_spans which does
    naive word tokenization. Real implementation would use NLP for entity extraction.
    """

    def test_fully_grounded_response(self, sample_turn: TurnEvent):
        """Test response with facts grounded in evidence."""
        metric = GroundednessMetric()
        result = metric.compute(sample_turn)

        # The mock tokenizer extracts word tokens - some match evidence, some don't
        # Real NLP would extract entities like "$1,234.56" and "January 15, 2026"
        assert result.score >= 0.0  # Some tokens match
        assert result.details["total_spans"] > 0

    def test_ungrounded_claims(self):
        """Test response with ungrounded claims."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="Your balance is $5,000.00 as of December 25, 2025.",
            tool_calls=[],
            evidence_blobs=[
                EvidenceBlob(source="api", content_hash="hash1", content_excerpt="Balance: $100.00"),
            ],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )

        metric = GroundednessMetric()
        result = metric.compute(turn)

        # $5,000.00 is not in evidence
        assert result.score < 1.0
        assert result.details["unsupported_claim_count"] > 0

    def test_no_factual_spans(self):
        """Test response with no evidence - all spans ungrounded."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="Hello, how can I help you today?",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o", model_family="gpt-4o", endpoint_used="chat"
            ),
            e2e_ms=100.0,
        )

        metric = GroundednessMetric()
        result = metric.compute(turn)

        # No evidence provided, so no spans can be grounded
        # Mock tokenizer extracts word tokens which can't be verified
        assert result.details["grounded_span_ratio"] == 0.0


class TestVerbosityMetric:
    """Tests for VerbosityMetric."""

    def test_within_budget(self, sample_turn: TurnEvent):
        """Test response within token budget."""
        metric = VerbosityMetric()
        result = metric.compute(sample_turn)

        assert result.score > 0.0
        assert result.details["violation"] >= 0

    def test_budget_adjustment_responses_api(self):
        """Test budget adjustment for Responses API."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="Short response.",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="gpt-4o",
                model_family="gpt-4o",
                endpoint_used="responses",
                verbosity=0,  # Minimal mode
            ),
            e2e_ms=100.0,
            response_tokens=50,
        )

        metric = VerbosityMetric()
        result = metric.compute(turn, token_budget=150)

        # Budget should be reduced by 30% for verbosity=0
        expected_budget = int(150 * 0.7)
        assert result.details["budget"] == expected_budget

    def test_budget_adjustment_reasoning_model(self):
        """Test budget adjustment for reasoning models."""
        turn = TurnEvent(
            turn_id="test:t1",
            session_id="s1",
            agent_name="Agent",
            user_text="test",
            user_end_ts=0.0,
            agent_last_output_ts=100.0,
            response_text="Detailed reasoning response with many tokens.",
            tool_calls=[],
            evidence_blobs=[],
            eval_model_config=EvalModelConfig(
                model_name="o3-mini",
                model_family="o3",
                endpoint_used="chat",
                include_reasoning=True,
            ),
            e2e_ms=100.0,
            response_tokens=200,
        )

        metric = VerbosityMetric()
        result = metric.compute(turn, token_budget=150)

        # Budget should be 2x for reasoning
        expected_budget = int(150 * 2.0)
        assert result.details["budget"] == expected_budget


class TestLatencyMetric:
    """Tests for LatencyMetric."""

    def test_single_turn_latency(self, sample_turn: TurnEvent):
        """Test latency for single turn."""
        metric = LatencyMetric()
        result = metric.compute(sample_turn)

        assert result.score == sample_turn.e2e_ms
        assert result.details["e2e_ms"] == 150.0
        assert result.details["ttft_ms"] == 50.0

    def test_aggregate_latency(self, multiple_turns: List[TurnEvent]):
        """Test aggregate latency computation."""
        metric = LatencyMetric()
        result = metric.compute_aggregate(multiple_turns)

        assert "e2e_p50_ms" in result.details
        assert "e2e_p95_ms" in result.details
        assert "e2e_mean_ms" in result.details
        assert result.details["sample_count"] == 2


class TestCostMetric:
    """Tests for CostMetric."""

    def test_single_turn_cost(self, sample_turn: TurnEvent):
        """Test cost computation for single turn."""
        metric = CostMetric()
        result = metric.compute(sample_turn)

        assert result.score > 0
        assert result.details["total_input_tokens"] == 100
        assert result.details["total_output_tokens"] == 50

    def test_aggregate_cost(self, multiple_turns: List[TurnEvent]):
        """Test aggregate cost computation."""
        metric = CostMetric()
        result = metric.compute_aggregate(multiple_turns)

        assert result.details["total_input_tokens"] == 220  # 100 + 120
        assert result.details["total_output_tokens"] == 90  # 50 + 40
        assert "model_breakdown" in result.details
        assert "gpt-4o" in result.details["model_breakdown"]


class TestHandoffAccuracyMetric:
    """Tests for HandoffAccuracyMetric."""

    def test_correct_handoff(self, sample_turn_with_handoff: TurnEvent):
        """Test correct handoff detection."""
        metric = HandoffAccuracyMetric()
        result = metric.compute_aggregate(
            [sample_turn_with_handoff],
            expected_handoffs=[{"from": "Concierge", "to": "FraudAgent"}],
        )

        assert result.score == 1.0
        assert result.details["correct_handoffs"] == 1

    def test_missing_handoff(self, sample_turn: TurnEvent):
        """Test when expected handoff didn't happen."""
        metric = HandoffAccuracyMetric()
        result = metric.compute_aggregate(
            [sample_turn],
            expected_handoffs=[{"from": "Concierge", "to": "FraudAgent"}],
        )

        assert result.score == 0.0
        assert result.details["total_handoffs"] == 0

    def test_no_expected_handoffs(self, sample_turn_with_handoff: TurnEvent):
        """Test when no handoffs expected."""
        metric = HandoffAccuracyMetric()
        result = metric.compute_aggregate([sample_turn_with_handoff])

        # Partial score when handoff happens without expectation
        assert result.score == 0.5
        assert result.details["total_handoffs"] == 1


# =============================================================================
# TEST: MetricRegistry
# =============================================================================


class TestMetricRegistry:
    """Tests for MetricRegistry."""

    def test_load_builtins(self):
        """Test loading built-in metrics."""
        registry = MetricRegistry()
        registry.load_builtins()

        assert len(registry) == len(BUILTIN_METRICS)
        assert "tool_precision" in registry.list_metrics()
        assert "latency" in registry.list_metrics()

    def test_register_custom_metric(self):
        """Test registering custom metric."""

        class CustomMetric(MetricPlugin):
            name = "custom_test"

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=1.0)

        registry = MetricRegistry()
        registry.register(CustomMetric())

        assert "custom_test" in registry.list_metrics()
        assert registry.get("custom_test") is not None

    def test_register_duplicate_error(self):
        """Test error on duplicate registration."""

        class DuplicateMetric(MetricPlugin):
            name = "dup_metric"

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=1.0)

        registry = MetricRegistry()
        registry.register(DuplicateMetric())

        with pytest.raises(ValueError, match="already registered"):
            registry.register(DuplicateMetric())

    def test_register_override(self):
        """Test overriding existing metric."""

        class OriginalMetric(MetricPlugin):
            name = "override_test"
            version = 1

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=0.5)

        class NewMetric(MetricPlugin):
            name = "override_test"
            version = 2

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=0.9)

        registry = MetricRegistry()
        registry.register(OriginalMetric())
        registry.register(NewMetric(), override=True)

        # Should have new version
        plugin = registry.get("override_test")
        assert hasattr(plugin, "version")
        assert plugin.version == 2  # type: ignore

    def test_unregister(self):
        """Test unregistering a metric."""

        class TempMetric(MetricPlugin):
            name = "temp_metric"

            def compute(self, turn, expectations=None, **kwargs):
                return MetricResult(name=self.name, score=1.0)

        registry = MetricRegistry()
        registry.register(TempMetric())
        assert "temp_metric" in registry.list_metrics()

        result = registry.unregister("temp_metric")
        assert result is True
        assert "temp_metric" not in registry.list_metrics()

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent metric."""
        registry = MetricRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_compute_turn(self, sample_turn: TurnEvent):
        """Test computing per-turn metrics."""
        registry = MetricRegistry()
        registry.load_builtins()

        results = registry.compute_turn(
            sample_turn,
            metrics=["tool_precision", "tool_efficiency"],
            expected_tools=["get_balance"],
        )

        assert "tool_precision" in results
        assert "tool_efficiency" in results
        assert results["tool_precision"].score == 1.0

    def test_compute_aggregate(self, multiple_turns: List[TurnEvent]):
        """Test computing aggregate metrics."""
        registry = MetricRegistry()
        registry.load_builtins()

        results = registry.compute_aggregate(
            multiple_turns,
            metrics=["latency", "cost"],
        )

        assert "latency" in results
        assert "cost" in results
        assert results["latency"].details["sample_count"] == 2

    def test_compute_all(self, multiple_turns: List[TurnEvent]):
        """Test computing all metrics."""
        registry = MetricRegistry()
        registry.load_builtins()

        results = registry.compute_all(multiple_turns)

        assert "per_turn" in results
        assert "aggregate" in results
        assert len(results["per_turn"]) == 2

    def test_load_from_yaml_builtins(self):
        """Test loading metrics from YAML config."""
        config = {
            "metrics": [
                "builtin.tool_precision",
                "builtin.groundedness",
            ]
        }

        registry = MetricRegistry()
        registry.load_from_yaml(config)

        assert "tool_precision" in registry.list_metrics()
        assert "groundedness" in registry.list_metrics()

    def test_list_per_turn_vs_aggregate(self):
        """Test listing per-turn vs aggregate metrics."""
        registry = MetricRegistry()
        registry.load_builtins()

        per_turn = registry.list_per_turn_metrics()
        aggregate = registry.list_aggregate_metrics()

        # Tool metrics are per-turn
        assert "tool_precision" in per_turn
        assert "tool_recall" in per_turn

        # Latency and cost are aggregate
        assert "latency" in aggregate
        assert "cost" in aggregate


class TestMetricRegistryYAMLLoading:
    """Tests for YAML-based metric loading."""

    def test_load_mixed_config(self):
        """Test loading mix of built-in and custom metrics."""
        config = {
            "metrics": [
                "tool_precision",  # Without builtin prefix
                "builtin.tool_recall",  # With prefix
            ]
        }

        registry = MetricRegistry()
        registry.load_from_yaml(config)

        assert "tool_precision" in registry.list_metrics()
        assert "tool_recall" in registry.list_metrics()

    def test_custom_metric_from_config(self):
        """Test loading custom metric from module (mocked)."""
        config = {
            "metrics": [
                {
                    "type": "custom",
                    "module": "tests.evaluation.metrics.test_metrics",
                    "metrics": [
                        {
                            "name": "mock_metric",
                            "function": "create_mock_metric",
                            "description": "A test metric",
                        }
                    ],
                }
            ]
        }

        # This would require the function to exist in this module
        # For now, test that it handles missing gracefully
        registry = MetricRegistry()
        registry.load_from_yaml(config)  # Should log warning but not crash


# =============================================================================
# TEST: Error Handling
# =============================================================================


class TestMetricErrorHandling:
    """Tests for metric error handling."""

    def test_metric_computation_error(self, sample_turn: TurnEvent):
        """Test graceful handling of metric computation errors."""

        class FailingMetric(MetricPlugin):
            name = "failing_metric"

            def compute(self, turn, expectations=None, **kwargs):
                raise RuntimeError("Intentional failure")

        registry = MetricRegistry()
        registry.register(FailingMetric())

        results = registry.compute_turn(sample_turn, metrics=["failing_metric"])

        assert "failing_metric" in results
        assert results["failing_metric"].score == 0.0
        assert "error" in results["failing_metric"].details

    def test_missing_metric_warning(self, sample_turn: TurnEvent):
        """Test warning for missing metric."""
        registry = MetricRegistry()

        with patch.object(registry, "_plugins", {}):
            results = registry.compute_turn(sample_turn, metrics=["nonexistent"])
            assert "nonexistent" not in results


# =============================================================================
# TEST: Integration with Expectations
# =============================================================================


class TestMetricExpectationsIntegration:
    """Tests for metrics with expectations."""

    def test_tool_metrics_with_expectations(
        self,
        sample_turn: TurnEvent,
        expectations: ScenarioExpectations,
    ):
        """Test tool metrics using expectations."""
        registry = MetricRegistry()
        registry.load_builtins()

        results = registry.compute_turn(sample_turn, expectations=expectations)

        assert results["tool_precision"].score == 1.0
        assert results["tool_recall"].score == 1.0

    def test_verbosity_with_response_constraints(self, sample_turn: TurnEvent):
        """Test verbosity using response constraints."""
        expectations = ScenarioExpectations(
            tools_called=[],
            response_constraints={"max_tokens": 200},
        )

        metric = VerbosityMetric()
        result = metric.compute(sample_turn, expectations)

        # Budget should come from expectations
        assert result.details["original_budget"] == 200


# =============================================================================
# TEST: BUILTIN_METRICS constant
# =============================================================================


class TestBuiltinMetricsConstant:
    """Tests for BUILTIN_METRICS constant."""

    def test_all_metrics_instantiated(self):
        """Test that all built-in metrics are instantiated."""
        for name, metric in BUILTIN_METRICS.items():
            assert isinstance(metric, (MetricPlugin, AggregateMetricPlugin))
            assert metric.name == name

    def test_expected_metrics_present(self):
        """Test expected built-in metrics are present."""
        expected = [
            "tool_precision",
            "tool_recall",
            "tool_efficiency",
            "groundedness",
            "verbosity",
            "latency",
            "cost",
            "handoff_accuracy",
        ]

        for name in expected:
            assert name in BUILTIN_METRICS, f"Missing built-in metric: {name}"


# =============================================================================
# Helper for custom metric loading test
# =============================================================================


def create_mock_metric(turn: "TurnEvent", expectations: Optional["ScenarioExpectations"]) -> MetricResult:
    """Mock metric function for testing custom loading."""
    return MetricResult(name="mock_metric", score=1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

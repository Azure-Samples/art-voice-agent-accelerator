"""
Built-in Metric Plugins
=======================

Extracts standard metrics from MetricsScorer as pluggable components.

Metrics:
- ToolPrecisionMetric: executed_expected / executed_total
- ToolRecallMetric: executed_expected / expected_total
- ToolEfficiencyMetric: 1 - (redundant_calls / total_calls)
- GroundednessMetric: grounded_span_ratio via string matching
- VerbosityMetric: token budget compliance (API-aware)
- LatencyMetric: E2E and TTFT percentiles (aggregate)
- CostMetric: Token cost analysis (aggregate)
- HandoffAccuracyMetric: Routing accuracy (aggregate)
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import numpy as np

from tests.evaluation.metrics.base import (
    AggregateMetricPlugin,
    MetricPlugin,
    MetricResult,
    metric_plugin,
)

if TYPE_CHECKING:
    from tests.evaluation.schemas import ScenarioExpectations, TurnEvent


# =============================================================================
# TOOL METRICS
# =============================================================================


@metric_plugin
class ToolPrecisionMetric(MetricPlugin):
    """
    Compute tool call precision.

    precision = executed_expected / executed_total

    High precision means the agent doesn't call unnecessary tools.
    """

    name = "tool_precision"
    description = "Fraction of called tools that were expected"
    higher_is_better = True
    default_threshold = 0.8

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        actual_calls = [tc.name for tc in turn.tool_calls]
        expected_calls = kwargs.get("expected_tools", [])

        if expectations and expectations.tools_called:
            expected_calls = expectations.tools_called

        if not actual_calls:
            score = 1.0 if not expected_calls else 0.0
        else:
            executed_expected = len(set(actual_calls) & set(expected_calls))
            score = executed_expected / len(actual_calls)

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "actual_tools": actual_calls,
                "expected_tools": expected_calls,
                "matched": list(set(actual_calls) & set(expected_calls)),
                "unexpected": list(set(actual_calls) - set(expected_calls)),
            },
        )


@metric_plugin
class ToolRecallMetric(MetricPlugin):
    """
    Compute tool call recall.

    recall = executed_expected / expected_total

    High recall means the agent calls all required tools.
    """

    name = "tool_recall"
    description = "Fraction of expected tools that were actually called"
    higher_is_better = True
    default_threshold = 0.9

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        actual_calls = [tc.name for tc in turn.tool_calls]
        expected_calls = kwargs.get("expected_tools", [])

        if expectations and expectations.tools_called:
            expected_calls = expectations.tools_called

        if not expected_calls:
            score = 1.0  # No expectations to miss
        else:
            executed_expected = len(set(actual_calls) & set(expected_calls))
            score = executed_expected / len(expected_calls)

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "actual_tools": actual_calls,
                "expected_tools": expected_calls,
                "matched": list(set(actual_calls) & set(expected_calls)),
                "missing": list(set(expected_calls) - set(actual_calls)),
            },
        )


@metric_plugin
class ToolEfficiencyMetric(MetricPlugin):
    """
    Compute tool call efficiency (penalize redundant calls).

    efficiency = 1 - (redundant_calls / total_calls)

    Redundant = same tool+args within 30s window.
    """

    name = "tool_efficiency"
    description = "Fraction of non-redundant tool calls"
    higher_is_better = True
    default_threshold = 0.95

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        if not turn.tool_calls:
            return MetricResult(
                name=self.name,
                score=1.0,
                details={"total_calls": 0, "redundant_calls": 0},
            )

        seen: Dict[str, float] = {}  # (tool_name, args_hash) -> timestamp
        redundant = 0
        redundant_details: List[str] = []

        for tc in turn.tool_calls:
            # Hash arguments for deduplication
            args_hash = hashlib.sha256(str(sorted(tc.arguments.items())).encode()).hexdigest()[:16]

            key = f"{tc.name}:{args_hash}"

            if key in seen and (tc.start_ts - seen[key]) < 30:
                redundant += 1
                redundant_details.append(tc.name)

            seen[key] = tc.start_ts

        score = 1.0 - (redundant / len(turn.tool_calls))

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "total_calls": len(turn.tool_calls),
                "redundant_calls": redundant,
                "redundant_tools": redundant_details,
            },
        )


# =============================================================================
# GROUNDEDNESS METRICS
# =============================================================================


@metric_plugin
class GroundednessMetric(MetricPlugin):
    """
    Compute groundedness score using cheap string matching.

    Checks if factual spans in response appear in:
    - Tool outputs (from evidence_blobs)
    - Context data (caller_name, customer_intelligence, etc.)
    """

    name = "groundedness"
    description = "Fraction of factual claims grounded in evidence"
    higher_is_better = True
    default_threshold = 0.7

    def extract_factual_spans(self, text: str) -> Set[str]:
        """Extract factual spans from text using regex heuristics."""
        spans: Set[str] = set()

        # Numbers (amounts, IDs, dates)
        spans.update(re.findall(r"\$?[\d,]+\.?\d*", text))

        # Dates (simple patterns)
        spans.update(re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text))
        spans.update(
            re.findall(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
                text,
            )
        )

        # Proper nouns (capitalized sequences)
        common_words = {"I", "The", "A", "An", "This", "That", "These", "Those"}
        proper_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        spans.update(pn for pn in proper_nouns if pn not in common_words)

        return spans

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        spans = self.extract_factual_spans(turn.response_text)

        if not spans:
            return MetricResult(
                name=self.name,
                score=1.0,
                details={
                    "grounded_span_ratio": 1.0,
                    "unsupported_claim_count": 0,
                    "total_spans": 0,
                    "spans_extracted": [],
                },
            )

        # Build evidence corpus
        evidence_text = " ".join(blob.content_excerpt for blob in turn.evidence_blobs)

        # Check each span
        grounded_count = 0
        grounded_spans: List[str] = []
        unsupported_spans: List[str] = []

        for span in spans:
            if span.lower() in evidence_text.lower():
                grounded_count += 1
                grounded_spans.append(span)
            else:
                unsupported_spans.append(span)

        score = grounded_count / len(spans)

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "grounded_span_ratio": score,
                "unsupported_claim_count": len(unsupported_spans),
                "total_spans": len(spans),
                "grounded_spans": grounded_spans,
                "unsupported_spans": unsupported_spans,
            },
        )


# =============================================================================
# VERBOSITY METRICS
# =============================================================================


@metric_plugin
class VerbosityMetric(MetricPlugin):
    """
    Compute verbosity score with API-aware budget adjustments.

    For Responses API:
    - verbosity=0: 30% smaller budget
    - verbosity=2: 50% larger budget

    For reasoning models (o1/o3/o4):
    - include_reasoning=true: 2x budget
    """

    name = "verbosity"
    description = "Token budget compliance score"
    higher_is_better = True
    default_threshold = 0.8

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        # Get base budget from expectations or default
        budget = 150
        if expectations and expectations.response_constraints:
            budget = expectations.response_constraints.get("max_tokens", 150)

        budget = kwargs.get("token_budget", budget)

        response_tokens = turn.response_tokens or len(turn.response_text.split())
        endpoint = turn.eval_model_config.endpoint_used

        original_budget = budget

        # Adjust budget for Responses API verbosity
        if endpoint == "responses":
            verbosity_level = (
                turn.eval_model_config.verbosity if turn.eval_model_config.verbosity is not None else 1
            )
            if verbosity_level == 0:
                budget = int(budget * 0.7)  # 30% reduction for minimal mode
            elif verbosity_level == 2:
                budget = int(budget * 1.5)  # 50% increase for detailed mode

        # Adjust for reasoning models
        model_family = turn.eval_model_config.model_family
        if model_family in ["o1", "o3", "o4"]:
            include_reasoning = turn.eval_model_config.include_reasoning or False
            if include_reasoning:
                budget = int(budget * 2.0)  # 2x budget for reasoning tokens

        violation = max(0, response_tokens - budget)
        score = 1.0 - min(violation / budget, 1.0) if budget > 0 else 0.0

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "tokens": response_tokens,
                "budget": budget,
                "original_budget": original_budget,
                "violation": violation,
                "api_adjusted": endpoint == "responses",
                "model_family": model_family,
            },
        )


# =============================================================================
# AGGREGATE METRICS (Multi-turn)
# =============================================================================


@metric_plugin
class LatencyMetric(AggregateMetricPlugin):
    """
    Compute latency percentiles across turns.

    Returns P50/P95/P99 for both E2E and TTFT.
    """

    name = "latency"
    description = "Response latency percentiles"
    higher_is_better = False  # Lower latency is better

    def compute_aggregate(
        self,
        turns: List["TurnEvent"],
        **kwargs: Any,
    ) -> MetricResult:
        e2e_times = [t.e2e_ms for t in turns if t.e2e_ms is not None]
        ttft_times = [t.ttft_ms for t in turns if t.ttft_ms is not None]

        details: Dict[str, Any] = {
            "sample_count": len(turns),
            "e2e_sample_count": len(e2e_times),
            "ttft_sample_count": len(ttft_times),
        }

        # Primary score is E2E P95 (common SLA target)
        score = 0.0

        if e2e_times:
            details["e2e_p50_ms"] = float(np.percentile(e2e_times, 50))
            details["e2e_p95_ms"] = float(np.percentile(e2e_times, 95))
            details["e2e_p99_ms"] = float(np.percentile(e2e_times, 99))
            details["e2e_mean_ms"] = float(np.mean(e2e_times))
            score = details["e2e_p95_ms"]

        if ttft_times:
            details["ttft_p50_ms"] = float(np.percentile(ttft_times, 50))
            details["ttft_p95_ms"] = float(np.percentile(ttft_times, 95))
            details["ttft_mean_ms"] = float(np.mean(ttft_times))

        return MetricResult(
            name=self.name,
            score=score,
            details=details,
        )

    # For compatibility with per-turn interface
    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        """Compute latency for a single turn."""
        return MetricResult(
            name=self.name,
            score=turn.e2e_ms or 0.0,
            details={
                "e2e_ms": turn.e2e_ms,
                "ttft_ms": turn.ttft_ms,
            },
        )


@metric_plugin
class CostMetric(AggregateMetricPlugin):
    """
    Compute cost analysis across turns.

    Uses OpenAI/Azure pricing (Jan 2026) per 1K tokens.
    """

    name = "cost"
    description = "Token cost analysis"
    higher_is_better = False  # Lower cost is better

    # Pricing per 1K tokens (Jan 2026)
    PRICING = {
        # GPT-4.1 series
        "gpt-4.1": {"input_per_1k": 0.002, "output_per_1k": 0.008},
        "gpt-4.1-mini": {"input_per_1k": 0.0004, "output_per_1k": 0.0016},
        "gpt-4.1-nano": {"input_per_1k": 0.0001, "output_per_1k": 0.0004},
        # GPT-4o series
        "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
        "gpt-4o-2024-08-06": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
        "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
        # o-series reasoning models
        "o1": {"input_per_1k": 0.015, "output_per_1k": 0.06},
        "o1-preview": {"input_per_1k": 0.015, "output_per_1k": 0.06},
        "o1-mini": {"input_per_1k": 0.0011, "output_per_1k": 0.0044},
        "o3": {"input_per_1k": 0.002, "output_per_1k": 0.008},
        "o3-mini": {"input_per_1k": 0.0011, "output_per_1k": 0.0044},
        "o4-mini": {"input_per_1k": 0.0011, "output_per_1k": 0.0044},
        # Legacy GPT-4
        "gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.06},
        "gpt-4-turbo": {"input_per_1k": 0.01, "output_per_1k": 0.03},
        # GPT-3.5
        "gpt-3.5-turbo": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
        # Default fallback
        "default": {"input_per_1k": 0.002, "output_per_1k": 0.008},
    }

    def compute_aggregate(
        self,
        turns: List["TurnEvent"],
        **kwargs: Any,
    ) -> MetricResult:
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        model_breakdown: Dict[str, Dict[str, Any]] = {}

        for turn in turns:
            input_tok = turn.input_tokens or 0
            output_tok = turn.response_tokens or 0
            reasoning_tok = turn.reasoning_tokens or 0

            total_input_tokens += input_tok
            total_output_tokens += output_tok
            total_reasoning_tokens += reasoning_tok

            model_name = turn.eval_model_config.model_name
            endpoint = turn.eval_model_config.endpoint_used

            if model_name not in model_breakdown:
                model_breakdown[model_name] = {
                    "endpoint": endpoint,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost_usd": 0.0,
                }

            breakdown = model_breakdown[model_name]
            breakdown["input_tokens"] += input_tok
            breakdown["output_tokens"] += output_tok
            breakdown["reasoning_tokens"] += reasoning_tok

            # Get pricing for this model
            model_pricing = self.PRICING.get(model_name, self.PRICING["default"])
            breakdown["cost_usd"] += (input_tok / 1000) * model_pricing.get(
                "input_per_1k", 0
            ) + ((output_tok + reasoning_tok) / 1000) * model_pricing.get("output_per_1k", 0)

        total_cost = sum(b["cost_usd"] for b in model_breakdown.values())
        cost_per_turn = total_cost / len(turns) if turns else 0

        return MetricResult(
            name=self.name,
            score=total_cost,  # Primary score is total cost
            details={
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "reasoning_tokens": total_reasoning_tokens,
                "estimated_cost_usd": round(total_cost, 4),
                "cost_per_turn_usd": round(cost_per_turn, 6),
                "model_breakdown": model_breakdown,
            },
        )

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        """Compute cost for a single turn."""
        return self.compute_aggregate([turn], **kwargs)


@metric_plugin
class HandoffAccuracyMetric(AggregateMetricPlugin):
    """
    Compute handoff routing accuracy.

    Checks if agent handoffs match expected routing.
    """

    name = "handoff_accuracy"
    description = "Agent handoff routing accuracy"
    higher_is_better = True
    default_threshold = 1.0

    def compute_aggregate(
        self,
        turns: List["TurnEvent"],
        **kwargs: Any,
    ) -> MetricResult:
        expected_handoffs = kwargs.get("expected_handoffs", [])
        handoffs = [t.handoff for t in turns if t.handoff is not None]

        if not expected_handoffs:
            return MetricResult(
                name=self.name,
                score=1.0 if not handoffs else 0.5,  # No expectations = partial score
                details={
                    "total_handoffs": len(handoffs),
                    "correct_handoffs": None,
                    "handoff_accuracy": None,
                    "actual_handoffs": [
                        {"from": h.source_agent, "to": h.target_agent} for h in handoffs
                    ],
                },
            )

        correct = 0
        matched_expected = []
        unmatched_expected = []

        for expected in expected_handoffs:
            found = False
            for handoff in handoffs:
                if handoff.source_agent == expected["from"] and handoff.target_agent == expected["to"]:
                    correct += 1
                    matched_expected.append(expected)
                    found = True
                    break
            if not found:
                unmatched_expected.append(expected)

        score = correct / len(expected_handoffs) if expected_handoffs else 1.0

        return MetricResult(
            name=self.name,
            score=score,
            details={
                "total_handoffs": len(handoffs),
                "expected_handoffs": len(expected_handoffs),
                "correct_handoffs": correct,
                "matched": matched_expected,
                "missing": unmatched_expected,
                "actual_handoffs": [{"from": h.source_agent, "to": h.target_agent} for h in handoffs],
            },
        )

    def compute(
        self,
        turn: "TurnEvent",
        expectations: Optional["ScenarioExpectations"] = None,
        **kwargs: Any,
    ) -> MetricResult:
        """Compute handoff info for a single turn."""
        if turn.handoff:
            return MetricResult(
                name=self.name,
                score=1.0,
                details={
                    "has_handoff": True,
                    "from": turn.handoff.source_agent,
                    "to": turn.handoff.target_agent,
                },
            )
        return MetricResult(
            name=self.name,
            score=1.0,
            details={"has_handoff": False},
        )


# =============================================================================
# REGISTRY OF ALL BUILT-IN METRICS
# =============================================================================

BUILTIN_METRICS: Dict[str, MetricPlugin] = {
    "tool_precision": ToolPrecisionMetric(),
    "tool_recall": ToolRecallMetric(),
    "tool_efficiency": ToolEfficiencyMetric(),
    "groundedness": GroundednessMetric(),
    "verbosity": VerbosityMetric(),
    "latency": LatencyMetric(),
    "cost": CostMetric(),
    "handoff_accuracy": HandoffAccuracyMetric(),
}


__all__ = [
    "ToolPrecisionMetric",
    "ToolRecallMetric",
    "ToolEfficiencyMetric",
    "GroundednessMetric",
    "VerbosityMetric",
    "LatencyMetric",
    "CostMetric",
    "HandoffAccuracyMetric",
    "BUILTIN_METRICS",
]

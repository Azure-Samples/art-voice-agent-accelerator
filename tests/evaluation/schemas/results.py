"""
Evaluation Result Schemas
=========================

Models for scoring and summarizing evaluation results.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .events import EvalModelConfig


class TurnScore(BaseModel):
    """Computed scores for a single turn."""

    turn_id: str
    tool_precision: float = Field(
        ..., description="Precision: executed_expected / executed_total"
    )
    tool_recall: float = Field(
        ..., description="Recall: executed_expected / expected_total"
    )
    tool_efficiency: float = Field(
        ..., description="Efficiency: 1 - (redundant_calls / total_calls)"
    )
    grounded_span_ratio: float = Field(
        ..., description="Ratio of factual spans found in evidence"
    )
    unsupported_claim_count: int = Field(
        ..., description="Count of spans NOT found in evidence"
    )
    e2e_ms: float = Field(..., description="End-to-end latency (milliseconds)")
    ttft_ms: Optional[float] = Field(None, description="Time to first token (milliseconds)")
    verbosity_score: float = Field(..., description="Verbosity score (0-1, 1=within budget)")
    verbosity_tokens: int = Field(..., description="Actual response tokens")
    verbosity_budget: int = Field(..., description="Token budget used")


class PerTurnSummary(BaseModel):
    """Summary of a single turn for reporting."""

    turn_id: str
    agent_name: str
    model_used: str = Field(..., description="Model deployment actually used")
    e2e_ms: float
    tools_expected: List[str] = Field(
        default_factory=list, description="Expected tools from YAML"
    )
    tools_called: List[str] = Field(
        default_factory=list, description="Actually called tools"
    )
    tool_precision: float
    tool_recall: float
    grounded_span_ratio: float
    response_length: int = Field(..., description="Character count of response")
    error: Optional[str] = None


class RunSummary(BaseModel):
    """Aggregated metrics for a complete evaluation run."""

    run_id: str
    scenario_name: str
    agent_name: str
    total_turns: int
    eval_model_config: EvalModelConfig

    # Per-turn details for transparency
    per_turn_metrics: List[PerTurnSummary] = Field(
        default_factory=list, description="Per-turn breakdown for debugging"
    )

    # Aggregated metrics
    tool_metrics: Dict[str, Any] = Field(
        ...,
        description="Tool call metrics: total_calls, precision, recall, efficiency, redundant_calls",
    )
    latency_metrics: Dict[str, float] = Field(
        ..., description="Latency metrics: e2e_p50_ms, e2e_p95_ms, ttft_p50_ms, etc."
    )
    groundedness_metrics: Dict[str, float] = Field(
        ...,
        description="Groundedness metrics: avg_grounded_span_ratio, avg_unsupported_claims",
    )
    verbosity_metrics: Dict[str, Any] = Field(
        ..., description="Verbosity metrics: avg_response_tokens, budget_violations, etc."
    )
    handoff_metrics: Optional[Dict[str, Any]] = Field(
        None, description="Handoff metrics: total_handoffs, correct_handoffs, accuracy"
    )
    cost_analysis: Dict[str, Any] = Field(
        ...,
        description="Cost analysis: total tokens, estimated cost, breakdown by model",
    )

    # Metadata
    commit_sha: Optional[str] = None
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    pass_fail: Optional[bool] = Field(
        None, description="Overall pass/fail (if thresholds applied)"
    )


__all__ = [
    "TurnScore",
    "PerTurnSummary",
    "RunSummary",
]

"""
Evaluation Event Schemas
=========================

Pydantic models for evaluation events - completely independent of production code.

These schemas define the structure of events captured during orchestration evaluation,
supporting both Chat Completions API and Responses API configurations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Record of a single tool invocation during a turn."""

    name: str = Field(..., description="Tool name (e.g., 'analyze_recent_transactions')")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    start_ts: float = Field(..., description="Start timestamp (seconds since epoch)")
    end_ts: float = Field(..., description="End timestamp (seconds since epoch)")
    duration_ms: float = Field(..., description="Duration in milliseconds")
    status: str = Field(default="success", description="'success' or 'error'")
    result_summary: Optional[str] = Field(
        None, description="First 200 chars of result (for debugging)"
    )
    result_hash: str = Field(..., description="SHA256 hash of result (for deduplication)")


class EvidenceBlob(BaseModel):
    """Evidence source for groundedness checking."""

    source: str = Field(..., description="Source identifier: 'tool:<tool_name>' or 'context:<key>'")
    content_hash: str = Field(..., description="SHA256 hash of content")
    content_excerpt: str = Field(..., description="First 200 chars of content")


class HandoffEvent(BaseModel):
    """Record of an agent handoff."""

    source_agent: str = Field(..., description="Agent that initiated handoff")
    target_agent: str = Field(..., description="Agent receiving handoff")
    tool_name: Optional[str] = Field(None, description="Handoff tool used (if applicable)")
    handoff_type: str = Field(
        default="discrete", description="'discrete' (tool-based) or 'announced' (greeting-based)"
    )
    context: Optional[str] = Field(None, description="Handoff context/reason")
    timestamp: float = Field(..., description="Handoff timestamp")


class EvalModelConfig(BaseModel):
    """Model configuration used for the turn - handles both API types."""

    model_name: str = Field(..., description="Deployment ID (e.g., 'gpt-4o', 'o1-preview')")
    model_family: Optional[str] = Field(
        None, description="Model family: 'gpt-4', 'gpt-5', 'o1', 'o3', 'o4'"
    )
    endpoint_used: str = Field(..., description="'chat' (Chat Completions) or 'responses'")

    # Chat Completions API parameters
    temperature: Optional[float] = Field(None, description="Temperature (Chat API only)")
    top_p: Optional[float] = Field(None, description="Top-p sampling (Chat API only)")
    max_tokens: Optional[int] = Field(None, description="Max tokens (Chat API)")

    # Responses API parameters
    max_completion_tokens: Optional[int] = Field(
        None, description="Max completion tokens (Responses API)"
    )
    verbosity: Optional[int] = Field(
        None, description="Verbosity level: 0=minimal, 1=standard, 2=detailed (Responses API)"
    )
    reasoning_effort: Optional[str] = Field(
        None, description="Reasoning effort: 'low', 'medium', 'high' (o1/o3/o4 only)"
    )
    include_reasoning: Optional[bool] = Field(
        None, description="Include reasoning tokens in response (o1/o3/o4 only)"
    )

    # Newer sampling params (GPT-5+)
    min_p: Optional[float] = Field(None, description="Minimum probability threshold")
    typical_p: Optional[float] = Field(None, description="Typical sampling")


class TurnEvent(BaseModel):
    """Complete record of a single conversation turn."""

    # Identifiers
    session_id: str = Field(..., description="Session/run identifier")
    turn_id: str = Field(..., description="Unique turn identifier")
    scenario_name: Optional[str] = Field(None, description="Scenario name (if from test suite)")

    # Timing
    user_end_ts: float = Field(..., description="User input end timestamp")
    agent_first_output_ts: Optional[float] = Field(
        None, description="First token from agent (TTFT)"
    )
    agent_last_output_ts: float = Field(..., description="Last output timestamp")
    e2e_ms: float = Field(..., description="End-to-end turn time (milliseconds)")
    ttft_ms: Optional[float] = Field(None, description="Time to first token (milliseconds)")

    # Agent state
    agent_name: str = Field(..., description="Active agent for this turn")
    previous_agent: Optional[str] = Field(None, description="Previous agent (if handoff occurred)")

    # Content
    user_text: str = Field(..., description="User input text")
    response_text: str = Field(..., description="Agent response text")
    response_tokens: Optional[int] = Field(None, description="Response token count")
    input_tokens: Optional[int] = Field(None, description="Input token count")
    reasoning_tokens: Optional[int] = Field(
        None, description="Reasoning tokens (o1/o3/o4 with include_reasoning=true)"
    )

    # Tool calls
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools called this turn")

    # Evidence (for groundedness checking)
    evidence_blobs: List[EvidenceBlob] = Field(
        default_factory=list, description="Evidence sources for grounding validation"
    )

    # Handoff (if occurred)
    handoff: Optional[HandoffEvent] = Field(None, description="Handoff event (if occurred)")

    # Model configuration
    eval_model_config: EvalModelConfig = Field(..., description="Model configuration used")

    # Metadata
    commit_sha: Optional[str] = Field(None, description="Git commit SHA (for versioning)")
    error: Optional[str] = Field(None, description="Error message (if turn failed)")


class ScenarioExpectations(BaseModel):
    """Expected behavior for a scenario turn (used for validation)."""

    tools_called: List[str] = Field(
        default_factory=list, description="Expected tool names (required)"
    )
    tools_optional: List[str] = Field(
        default_factory=list, description="Optional tools (won't fail if missing)"
    )
    handoff: Optional[Dict[str, str]] = Field(
        None, description="Expected handoff: {'to_agent': 'AgentName'} or null"
    )
    response_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Response constraints: max_tokens, must_include, must_ask_for, etc.",
    )
    grounding_required: List[str] = Field(
        default_factory=list, description="Human-readable grounding requirements"
    )


class TurnScore(BaseModel):
    """Computed scores for a single turn."""

    turn_id: str
    tool_precision: float = Field(..., description="Precision: executed_expected / executed_total")
    tool_recall: float = Field(..., description="Recall: executed_expected / expected_total")
    tool_efficiency: float = Field(
        ..., description="Efficiency: 1 - (redundant_calls / total_calls)"
    )
    grounded_span_ratio: float = Field(
        ..., description="Ratio of factual spans found in evidence"
    )
    unsupported_claim_count: int = Field(..., description="Count of spans NOT found in evidence")
    e2e_ms: float = Field(..., description="End-to-end latency (milliseconds)")
    ttft_ms: Optional[float] = Field(None, description="Time to first token (milliseconds)")
    verbosity_score: float = Field(..., description="Verbosity score (0-1, 1=within budget)")
    verbosity_tokens: int = Field(..., description="Actual response tokens")
    verbosity_budget: int = Field(..., description="Token budget used")


class RunSummary(BaseModel):
    """Aggregated metrics for a complete evaluation run."""

    run_id: str
    scenario_name: str
    agent_name: str
    total_turns: int
    eval_model_config: EvalModelConfig

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
    "ToolCall",
    "EvidenceBlob",
    "HandoffEvent",
    "EvalModelConfig",
    "TurnEvent",
    "ScenarioExpectations",
    "TurnScore",
    "RunSummary",
]

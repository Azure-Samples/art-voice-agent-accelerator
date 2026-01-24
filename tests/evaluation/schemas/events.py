"""
Evaluation Event Schemas
========================

Pydantic models for evaluation events captured during orchestration evaluation.
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

    source: str = Field(
        ..., description="Source identifier: 'tool:<tool_name>' or 'context:<key>'"
    )
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
        None,
        description="Verbosity level: 0=minimal, 1=standard, 2=detailed (Responses API)",
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
    previous_agent: Optional[str] = Field(
        None, description="Previous agent (if handoff occurred)"
    )

    # Content
    user_text: str = Field(..., description="User input text")
    response_text: str = Field(..., description="Agent response text")
    response_tokens: Optional[int] = Field(None, description="Response token count")
    input_tokens: Optional[int] = Field(None, description="Input token count")
    reasoning_tokens: Optional[int] = Field(
        None, description="Reasoning tokens (o1/o3/o4 with include_reasoning=true)"
    )

    # Tool calls
    tool_calls: List[ToolCall] = Field(
        default_factory=list, description="Tools called this turn"
    )

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


__all__ = [
    "ToolCall",
    "EvidenceBlob",
    "HandoffEvent",
    "EvalModelConfig",
    "TurnEvent",
]

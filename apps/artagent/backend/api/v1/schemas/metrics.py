"""
Session Metrics API Schemas
===========================

Pydantic schemas for session telemetry and latency metrics.
These schemas support Phase 3 Dashboard Integration for the telemetry plan.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LatencyStats(BaseModel):
    """Statistical summary for a latency metric."""

    avg_ms: float = Field(..., description="Average latency in milliseconds")
    min_ms: float = Field(..., description="Minimum latency in milliseconds")
    max_ms: float = Field(..., description="Maximum latency in milliseconds")
    p50_ms: float | None = Field(None, description="50th percentile (median)")
    p95_ms: float | None = Field(None, description="95th percentile")
    p99_ms: float | None = Field(None, description="99th percentile")
    count: int = Field(..., description="Number of samples")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_ms": 142.5,
                "min_ms": 85.0,
                "max_ms": 312.0,
                "p50_ms": 125.0,
                "p95_ms": 280.0,
                "p99_ms": 305.0,
                "count": 15,
            }
        }
    )


class TurnMetrics(BaseModel):
    """Metrics for a single conversation turn."""

    turn_number: int = Field(..., description="Turn number in the conversation")
    stt_latency_ms: float | None = Field(None, description="Speech-to-text latency in milliseconds")
    llm_ttfb_ms: float | None = Field(None, description="LLM time-to-first-byte in milliseconds")
    llm_total_ms: float | None = Field(None, description="Total LLM response time in milliseconds")
    tts_ttfb_ms: float | None = Field(None, description="TTS time-to-first-audio in milliseconds")
    tts_total_ms: float | None = Field(None, description="Total TTS synthesis time in milliseconds")
    total_latency_ms: float | None = Field(
        None, description="End-to-end turn latency in milliseconds"
    )
    input_tokens: int | None = Field(None, description="LLM input token count")
    output_tokens: int | None = Field(None, description="LLM output token count")
    timestamp: float | None = Field(None, description="Unix timestamp of the turn")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "turn_number": 3,
                "stt_latency_ms": 450.0,
                "llm_ttfb_ms": 142.0,
                "llm_total_ms": 823.0,
                "tts_ttfb_ms": 89.0,
                "tts_total_ms": 312.0,
                "total_latency_ms": 1584.0,
                "input_tokens": 150,
                "output_tokens": 75,
                "timestamp": 1701360000.0,
            }
        }
    )


class TokenUsage(BaseModel):
    """Token usage summary for a session."""

    total_input_tokens: int = Field(0, description="Total input tokens across all turns")
    total_output_tokens: int = Field(0, description="Total output tokens across all turns")
    total_tokens: int = Field(0, description="Combined total tokens")
    avg_input_per_turn: float = Field(0.0, description="Average input tokens per turn")
    avg_output_per_turn: float = Field(0.0, description="Average output tokens per turn")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_input_tokens": 750,
                "total_output_tokens": 375,
                "total_tokens": 1125,
                "avg_input_per_turn": 150.0,
                "avg_output_per_turn": 75.0,
            }
        }
    )


class SessionMetricsResponse(BaseModel):
    """Complete session metrics response."""

    session_id: str = Field(..., description="The session identifier")
    call_connection_id: str | None = Field(None, description="ACS call connection ID if applicable")
    transport_type: str | None = Field(None, description="Transport type: 'ACS' or 'BROWSER'")
    turn_count: int = Field(0, description="Total number of conversation turns")
    session_duration_ms: float | None = Field(
        None, description="Total session duration in milliseconds"
    )

    # Latency summaries
    latency_summary: dict[str, LatencyStats] = Field(
        default_factory=dict,
        description="Latency statistics by stage (stt, llm_ttfb, llm_total, tts_ttfb, tts_total, total)",
    )

    # Token usage
    token_usage: TokenUsage | None = Field(None, description="Token usage summary for the session")

    # Per-turn breakdown (optional, can be large)
    turns: list[TurnMetrics] | None = Field(
        None, description="Detailed metrics per conversation turn"
    )

    # Status
    status: str = Field("active", description="Session status: 'active', 'completed', 'error'")
    error_count: int = Field(0, description="Number of errors during the session")

    # Timestamps
    start_time: float | None = Field(None, description="Session start Unix timestamp")
    end_time: float | None = Field(None, description="Session end Unix timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "abc123-def456",
                "call_connection_id": "411f1200-bc6f-402d-8b5c-0510972cb357",
                "transport_type": "ACS",
                "turn_count": 5,
                "session_duration_ms": 45000.0,
                "latency_summary": {
                    "stt": {
                        "avg_ms": 420.0,
                        "min_ms": 350.0,
                        "max_ms": 520.0,
                        "count": 5,
                    },
                    "llm_ttfb": {
                        "avg_ms": 142.0,
                        "min_ms": 98.0,
                        "max_ms": 210.0,
                        "count": 5,
                    },
                    "total": {
                        "avg_ms": 1584.0,
                        "min_ms": 1200.0,
                        "max_ms": 2100.0,
                        "count": 5,
                    },
                },
                "token_usage": {
                    "total_input_tokens": 750,
                    "total_output_tokens": 375,
                    "total_tokens": 1125,
                    "avg_input_per_turn": 150.0,
                    "avg_output_per_turn": 75.0,
                },
                "status": "active",
                "error_count": 0,
                "start_time": 1701360000.0,
            }
        }
    )


class ActiveSessionsResponse(BaseModel):
    """Response for listing active sessions with basic metrics."""

    total_active: int = Field(..., description="Total number of active sessions")
    media_sessions: int = Field(0, description="Active ACS media sessions")
    browser_sessions: int = Field(0, description="Active browser sessions")
    total_disconnected: int = Field(0, description="Total disconnected sessions")
    sessions: list[dict[str, Any]] = Field(
        default_factory=list, description="List of active session summaries"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_active": 3,
                "media_sessions": 2,
                "browser_sessions": 1,
                "total_disconnected": 15,
                "sessions": [
                    {
                        "session_id": "abc123",
                        "transport_type": "ACS",
                        "turn_count": 5,
                        "duration_ms": 45000,
                    }
                ],
            }
        }
    )

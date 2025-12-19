"""
Realtime API Schemas
===================

Pydantic schemas for realtime WebSocket communication endpoints.

This module provides comprehensive schemas for:
- WebSocket connection and status responses
- Dashboard relay configuration and status
- Conversation session management
- Real-time communication metadata
- Service health and monitoring

All schemas include proper validation, serialization, and OpenAPI documentation
support for the V1 realtime API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RealtimeStatusResponse(BaseModel):
    """
    Response schema for realtime service status endpoint.

    Provides comprehensive information about the realtime communication
    service including availability, features, and active connections.
    """

    status: str = Field(
        ...,
        description="Current service status",
        json_schema_extra={
            "example": "available",
            "enum": ["available", "degraded", "unavailable"],
        },
    )

    websocket_endpoints: dict[str, str] = Field(
        ...,
        description="Available WebSocket endpoints",
        json_schema_extra={
            "example": {
                "dashboard_relay": "/api/v1/realtime/dashboard/relay",
                "conversation": "/api/v1/realtime/conversation",
            }
        },
    )

    features: dict[str, bool] = Field(
        ...,
        description="Supported features and capabilities",
        json_schema_extra={
            "example": {
                "dashboard_broadcasting": True,
                "conversation_streaming": True,
                "orchestrator_support": True,
                "session_management": True,
            }
        },
    )

    active_connections: dict[str, int] = Field(
        ...,
        description="Current active connection counts",
        json_schema_extra={"example": {"dashboard_clients": 0, "conversation_sessions": 0}},
    )

    protocols_supported: list[str] = Field(
        default=["WebSocket"],
        description="Supported communication protocols",
        json_schema_extra={"example": ["WebSocket"]},
    )

    version: str = Field(
        default="v1", description="API version", json_schema_extra={"example": "v1"}
    )


class DashboardConnectionResponse(BaseModel):
    """
    Response schema for dashboard connection events.

    Provides information about dashboard client connections including
    client tracking, session details, and connection metadata.
    """

    client_id: str = Field(
        ...,
        description="Unique identifier for the dashboard client",
        json_schema_extra={"example": "abc123def"},
    )

    connection_time: datetime = Field(
        ...,
        description="Timestamp when the connection was established",
        json_schema_extra={"example": "2024-01-01T12:00:00Z"},
    )

    total_clients: int = Field(
        ...,
        description="Total number of connected dashboard clients",
        json_schema_extra={"example": 1},
        ge=0,
    )

    endpoint: str = Field(
        default="dashboard_relay",
        description="WebSocket endpoint used for connection",
        json_schema_extra={"example": "dashboard_relay"},
    )

    features_enabled: list[str] = Field(
        default=["broadcasting", "monitoring"],
        description="Features enabled for this dashboard connection",
        json_schema_extra={"example": ["broadcasting", "monitoring", "tracing"]},
    )


class ConversationSessionResponse(BaseModel):
    """
    Response schema for conversation session events.

    Provides comprehensive information about conversation sessions including
    session management, orchestrator details, and session state.
    """

    session_id: str = Field(
        ...,
        description="Unique identifier for the conversation session",
        json_schema_extra={"example": "conv_abc123def"},
    )

    start_time: datetime = Field(
        ...,
        description="Timestamp when the session was started",
        json_schema_extra={"example": "2024-01-01T12:00:00Z"},
    )

    orchestrator_name: str | None = Field(
        None,
        description="Name of the orchestrator handling this session",
        json_schema_extra={"example": "gpt-4-orchestrator"},
    )

    total_sessions: int = Field(
        ...,
        description="Total number of active conversation sessions",
        json_schema_extra={"example": 1},
        ge=0,
    )

    features_enabled: list[str] = Field(
        default=["stt", "tts", "conversation_memory"],
        description="Features enabled for this conversation session",
        json_schema_extra={
            "example": ["stt", "tts", "conversation_memory", "interruption_handling"]
        },
    )

    audio_config: dict[str, Any] | None = Field(
        None,
        description="Audio processing configuration for the session",
        json_schema_extra={
            "example": {
                "stt_language": "en-US",
                "tts_voice": "en-US-AriaNeural",
                "sample_rate": 24000,
            }
        },
    )

    memory_status: dict[str, Any] | None = Field(
        None,
        description="Conversation memory status and configuration",
        json_schema_extra={"example": {"enabled": True, "turn_count": 0, "context_length": 0}},
    )


class WebSocketMessageBase(BaseModel):
    """
    Base schema for WebSocket messages.

    Provides common fields for all WebSocket message types including
    message identification, typing, and metadata.
    """

    type: str = Field(
        ...,
        description="Message type identifier",
        json_schema_extra={"example": "status"},
    )

    timestamp: datetime | None = Field(
        None,
        description="Message timestamp",
        json_schema_extra={"example": "2024-01-01T12:00:00Z"},
    )

    session_id: str | None = Field(
        None,
        description="Associated session identifier",
        json_schema_extra={"example": "conv_abc123def"},
    )


class StatusMessage(WebSocketMessageBase):
    """
    WebSocket status message schema.

    Used for sending status updates and system messages
    to connected WebSocket clients.
    """

    type: str = Field(
        default="status",
        description="Message type - always 'status' for status messages",
        json_schema_extra={"example": "status"},
    )

    message: str = Field(
        ...,
        description="Status message content",
        json_schema_extra={"example": "Welcome to the conversation service"},
    )

    level: str = Field(
        default="info",
        description="Message level",
        json_schema_extra={"example": "info", "enum": ["info", "warning", "error"]},
    )


class ConversationMessage(WebSocketMessageBase):
    """
    WebSocket conversation message schema.

    Used for sending conversation messages between users and assistants
    including proper sender identification and content.
    """

    type: str = Field(
        default="conversation",
        description="Message type - always 'conversation' for conversation messages",
        json_schema_extra={"example": "conversation"},
    )

    sender: str = Field(
        ...,
        description="Message sender identifier",
        json_schema_extra={"example": "User", "enum": ["User", "Assistant", "System"]},
    )

    message: str = Field(
        ...,
        description="Conversation message content",
        json_schema_extra={"example": "Hello, how can I help you today?"},
    )

    language: str | None = Field(
        None,
        description="Detected or specified language code",
        json_schema_extra={"example": "en-US"},
    )


class StreamingMessage(WebSocketMessageBase):
    """
    WebSocket streaming message schema.

    Used for real-time streaming content including partial transcriptions,
    assistant responses, and other streaming data.
    """

    type: str = Field(
        default="streaming",
        description="Message type - always 'streaming' for streaming messages",
        json_schema_extra={"example": "streaming"},
    )

    content: str = Field(
        ...,
        description="Streaming content",
        json_schema_extra={"example": "This is a partial transcription..."},
    )

    is_final: bool = Field(
        default=False,
        description="Whether this is the final streaming message",
        json_schema_extra={"example": False},
    )

    streaming_type: str = Field(
        ...,
        description="Type of streaming content",
        json_schema_extra={
            "example": "stt_partial",
            "enum": [
                "stt_partial",
                "stt_final",
                "assistant_partial",
                "assistant_final",
            ],
        },
    )


class ErrorMessage(WebSocketMessageBase):
    """
    WebSocket error message schema.

    Used for communicating errors and exceptions to WebSocket clients
    with proper error classification and recovery information.
    """

    type: str = Field(
        default="error",
        description="Message type - always 'error' for error messages",
        json_schema_extra={"example": "error"},
    )

    error_code: str = Field(
        ...,
        description="Error code identifier",
        json_schema_extra={"example": "STT_ERROR"},
    )

    error_message: str = Field(
        ...,
        description="Human-readable error message",
        json_schema_extra={"example": "Speech-to-text service temporarily unavailable"},
    )

    error_type: str = Field(
        ...,
        description="Error classification",
        json_schema_extra={
            "example": "service_error",
            "enum": [
                "validation_error",
                "auth_error",
                "service_error",
                "network_error",
                "unknown_error",
            ],
        },
    )

    recovery_suggestion: str | None = Field(
        None,
        description="Suggested recovery action",
        json_schema_extra={"example": "Please try again in a few moments"},
    )

    is_recoverable: bool = Field(
        default=True,
        description="Whether the error condition is recoverable",
        json_schema_extra={"example": True},
    )


class AudioMetadata(BaseModel):
    """
    Audio processing metadata schema.

    Provides information about audio stream configuration,
    processing parameters, and quality metrics.
    """

    sample_rate: int = Field(
        ...,
        description="Audio sample rate in Hz",
        json_schema_extra={"example": 24000},
        gt=0,
    )

    channels: int = Field(
        default=1,
        description="Number of audio channels",
        json_schema_extra={"example": 1},
        ge=1,
        le=2,
    )

    bit_depth: int = Field(
        default=16,
        description="Audio bit depth",
        json_schema_extra={"example": 16, "enum": [16, 24, 32]},
    )

    format: str = Field(
        default="pcm",
        description="Audio format",
        json_schema_extra={"example": "pcm", "enum": ["pcm", "opus", "mp3"]},
    )

    language: str | None = Field(
        None, description="Audio language code", json_schema_extra={"example": "en-US"}
    )


class SessionMetrics(BaseModel):
    """
    Session performance metrics schema.

    Provides performance and quality metrics for conversation sessions
    including latency, accuracy, and processing statistics.
    """

    session_id: str = Field(
        ...,
        description="Session identifier for these metrics",
        json_schema_extra={"example": "conv_abc123def"},
    )

    duration_seconds: float = Field(
        ...,
        description="Session duration in seconds",
        json_schema_extra={"example": 120.5},
        ge=0,
    )

    message_count: int = Field(
        ...,
        description="Total number of messages exchanged",
        json_schema_extra={"example": 10},
        ge=0,
    )

    avg_response_time_ms: float = Field(
        ...,
        description="Average response time in milliseconds",
        json_schema_extra={"example": 250.5},
        ge=0,
    )

    stt_accuracy: float | None = Field(
        None,
        description="Speech-to-text accuracy percentage",
        json_schema_extra={"example": 95.2},
        ge=0,
        le=100,
    )

    tts_synthesis_time_ms: float | None = Field(
        None,
        description="Average TTS synthesis time in milliseconds",
        json_schema_extra={"example": 180.3},
        ge=0,
    )

    interruption_count: int = Field(
        default=0,
        description="Number of conversation interruptions",
        json_schema_extra={"example": 2},
        ge=0,
    )

    error_count: int = Field(
        default=0,
        description="Number of errors during session",
        json_schema_extra={"example": 0},
        ge=0,
    )

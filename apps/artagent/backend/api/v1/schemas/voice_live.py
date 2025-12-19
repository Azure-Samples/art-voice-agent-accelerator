"""
Live Voice API Schemas
======================

Pydantic schemas for Live Voice WebSocket communication and Azure AI Speech integration.

This module provides comprehensive schemas for:
- WebSocket connection and session management
- Live Voice configuration and settings
- Audio processing parameters
- Real-time communication messages
- Performance metrics and monitoring
- Azure AI Speech integration

All schemas include proper validation, serialization, and OpenAPI documentation
support for the V1 Live Voice API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field


class VoiceLiveStatusResponse(BaseModel):
    """
    Response schema for Live Voice service status endpoint.

    Provides comprehensive information about the Live Voice service
    including Azure AI Speech integration status, features, and connections.
    """

    status: str = Field(
        ...,
        description="Current Live Voice service status",
        json_schema_extra={
            "example": "available",
            "enum": ["available", "degraded", "unavailable"],
        },
    )

    azure_speech_status: str = Field(
        ...,
        description="Azure AI Speech integration status",
        json_schema_extra={
            "example": "connected",
            "enum": ["connected", "disconnected", "error", "unknown"],
        },
    )

    websocket_endpoints: dict[str, str] = Field(
        ...,
        description="Available WebSocket endpoints for Live Voice",
        json_schema_extra={
            "example": {
                "voice_live_session": "/api/v1/live-voice/session",
            }
        },
    )

    features: dict[str, bool] = Field(
        ...,
        description="Supported Live Voice features and capabilities",
        json_schema_extra={
            "example": {
                "real_time_audio": True,
                "voice_activity_detection": True,
                "noise_reduction": True,
                "echo_cancellation": True,
                "session_management": True,
                "ai_model_integration": True,
            }
        },
    )

    active_connections: dict[str, int] = Field(
        ...,
        description="Current active Live Voice connection counts",
        json_schema_extra={"example": {"voice_live_sessions": 0}},
    )

    protocols_supported: list[str] = Field(
        default=["WebSocket"],
        description="Supported communication protocols",
        json_schema_extra={"example": ["WebSocket"]},
    )

    version: str = Field(
        default="v1", description="API version", json_schema_extra={"example": "v1"}
    )


class VoiceLiveSessionResponse(BaseModel):
    """
    Response schema for Live Voice session events.

    Provides comprehensive information about Live Voice sessions including
    session management, configuration, and connection state.
    """

    model_config = ConfigDict()

    session_id: str = Field(
        ...,
        description="Unique identifier for the Live Voice session",
        json_schema_extra={"example": "lv_abc123def"},
    )

    start_time: datetime = Field(
        ...,
        description="Timestamp when the session was started",
        json_schema_extra={"example": "2024-01-01T12:00:00Z"},
    )

    status: str = Field(
        ...,
        description="Current session status",
        json_schema_extra={
            "example": "connected",
            "enum": [
                "initializing",
                "connected",
                "processing",
                "paused",
                "disconnecting",
                "disconnected",
                "error",
            ],
        },
    )

    azure_speech_connected: bool = Field(
        ...,
        description="Whether Azure AI Speech is connected",
        json_schema_extra={"example": True},
    )

    audio_config: dict[str, Any] = Field(
        ...,
        description="Audio processing configuration for the session",
        json_schema_extra={
            "example": {
                "sample_rate": 24000,
                "channels": 1,
                "format": "pcm",
                "language": "en-US",
                "vad_enabled": True,
                "noise_reduction": True,
            }
        },
    )

    model_configuration: dict[str, Any] = Field(
        ...,
        description="AI model configuration for the session",
        json_schema_extra={
            "example": {
                "model_name": "gpt-4",
                "voice_name": "en-US-AriaNeural",
                "temperature": 0.7,
                "max_tokens": 2000,
            }
        },
    )

    session_metrics: dict[str, Any] | None = Field(
        None,
        description="Session performance metrics",
        json_schema_extra={
            "example": {
                "total_messages": 0,
                "audio_bytes_processed": 0,
                "average_response_time_ms": 0.0,
                "error_count": 0,
            }
        },
    )


class VoiceLiveConfigRequest(BaseModel):
    """
    Request schema for Live Voice session configuration.

    Used to configure Live Voice sessions including audio parameters,
    AI model settings, and feature enablement.
    """

    # Audio Configuration
    audio_config: dict[str, Any] | None = Field(
        None,
        description="Audio processing configuration",
        json_schema_extra={
            "example": {
                "sample_rate": 24000,
                "channels": 1,
                "format": "pcm",
                "language": "en-US",
                "vad_enabled": True,
                "vad_sensitivity": 0.5,
                "noise_reduction": True,
                "echo_cancellation": True,
            }
        },
    )

    # Model Configuration
    model_configuration: dict[str, Any] | None = Field(
        None,
        description="AI model configuration",
        json_schema_extra={
            "example": {
                "model_name": "gpt-4",
                "deployment_name": "gpt-4-deployment",
                "temperature": 0.7,
                "max_tokens": 2000,
                "voice_name": "en-US-AriaNeural",
                "voice_style": "friendly",
                "system_instructions": "You are a helpful assistant.",
            }
        },
    )

    # Session Configuration
    session_config: dict[str, Any] | None = Field(
        None,
        description="Session-specific configuration",
        json_schema_extra={
            "example": {
                "user_id": "user123",
                "session_timeout_minutes": 30,
                "auto_disconnect_on_silence": True,
                "silence_timeout_seconds": 300,
            }
        },
    )


class VoiceLiveMessage(BaseModel):
    """
    Base schema for Live Voice WebSocket messages.

    Provides common fields for all Live Voice message types including
    message identification, typing, and session metadata.
    """

    type: str = Field(
        ...,
        description="Message type identifier",
        json_schema_extra={"example": "audio"},
    )

    timestamp: datetime | None = Field(
        None,
        description="Message timestamp",
        json_schema_extra={"example": "2024-01-01T12:00:00Z"},
    )

    session_id: str | None = Field(
        None,
        description="Associated session identifier",
        json_schema_extra={"example": "lv_abc123def"},
    )


class VoiceLiveAudioMessage(VoiceLiveMessage):
    """
    WebSocket audio message schema for Live Voice.

    Used for sending audio data and metadata between client and server
    in Live Voice sessions.
    """

    type: str = Field(
        default="audio",
        description="Message type - always 'audio' for audio messages",
        json_schema_extra={"example": "audio"},
    )

    audio_format: str = Field(
        ...,
        description="Audio format specification",
        json_schema_extra={"example": "pcm", "enum": ["pcm", "opus", "mp3", "wav"]},
    )

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

    chunk_size: int | None = Field(
        None,
        description="Size of audio chunk in bytes",
        json_schema_extra={"example": 1024},
        gt=0,
    )

    is_final: bool = Field(
        default=False,
        description="Whether this is the final audio chunk",
        json_schema_extra={"example": False},
    )

    language: str | None = Field(
        None, description="Audio language code", json_schema_extra={"example": "en-US"}
    )


class VoiceLiveTextMessage(VoiceLiveMessage):
    """
    WebSocket text message schema for Live Voice.

    Used for sending text content, transcriptions, and responses
    in Live Voice sessions.
    """

    type: str = Field(
        default="text",
        description="Message type - always 'text' for text messages",
        json_schema_extra={"example": "text"},
    )

    content: str = Field(
        ...,
        description="Text content",
        json_schema_extra={"example": "Hello, how can I help you?"},
    )

    role: str = Field(
        ...,
        description="Message role",
        json_schema_extra={
            "example": "assistant",
            "enum": ["user", "assistant", "system"],
        },
    )

    is_partial: bool = Field(
        default=False,
        description="Whether this is a partial message",
        json_schema_extra={"example": False},
    )

    confidence: float | None = Field(
        None,
        description="Confidence score for transcribed text (0.0 to 1.0)",
        json_schema_extra={"example": 0.95},
        ge=0.0,
        le=1.0,
    )

    language: str | None = Field(
        None,
        description="Detected language code",
        json_schema_extra={"example": "en-US"},
    )


class VoiceLiveControlMessage(VoiceLiveMessage):
    """
    WebSocket control message schema for Live Voice.

    Used for session control, configuration updates, and system commands
    in Live Voice sessions.
    """

    type: str = Field(
        default="control",
        description="Message type - always 'control' for control messages",
        json_schema_extra={"example": "control"},
    )

    command: str = Field(
        ...,
        description="Control command",
        json_schema_extra={
            "example": "start",
            "enum": ["start", "stop", "pause", "resume", "configure", "status", "ping"],
        },
    )

    parameters: dict[str, Any] | None = Field(
        None,
        description="Command parameters",
        json_schema_extra={"example": {"audio_enabled": True, "voice_activity_detection": True}},
    )


class VoiceLiveStatusMessage(VoiceLiveMessage):
    """
    WebSocket status message schema for Live Voice.

    Used for sending status updates, health checks, and system information
    to Live Voice session clients.
    """

    type: str = Field(
        default="status",
        description="Message type - always 'status' for status messages",
        json_schema_extra={"example": "status"},
    )

    status: str = Field(
        ...,
        description="Status value",
        json_schema_extra={
            "example": "connected",
            "enum": ["connected", "processing", "idle", "error", "disconnected"],
        },
    )

    message: str = Field(
        ...,
        description="Status message content",
        json_schema_extra={"example": "Live Voice session connected successfully"},
    )

    level: str = Field(
        default="info",
        description="Message level",
        json_schema_extra={
            "example": "info",
            "enum": ["info", "warning", "error", "success"],
        },
    )

    details: dict[str, Any] | None = Field(
        None,
        description="Additional status details",
        json_schema_extra={"example": {"azure_speech_connected": True, "model_loaded": True}},
    )


class VoiceLiveErrorMessage(VoiceLiveMessage):
    """
    WebSocket error message schema for Live Voice.

    Used for communicating errors and exceptions to Live Voice clients
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
        json_schema_extra={"example": "AZURE_SPEECH_ERROR"},
    )

    error_message: str = Field(
        ...,
        description="Human-readable error message",
        json_schema_extra={"example": "Azure AI Speech service temporarily unavailable"},
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
                "audio_error",
                "model_error",
                "session_error",
                "unknown_error",
            ],
        },
    )

    error_details: dict[str, Any] | None = Field(
        None,
        description="Additional error details",
        json_schema_extra={
            "example": {
                "service": "azure_speech",
                "endpoint": "voice_live",
                "retry_after": 30,
            }
        },
    )

    recovery_suggestion: str | None = Field(
        None,
        description="Suggested recovery action",
        json_schema_extra={"example": "Please check your internet connection and try again"},
    )

    is_recoverable: bool = Field(
        default=True,
        description="Whether the error condition is recoverable",
        json_schema_extra={"example": True},
    )


class VoiceLiveMetricsMessage(VoiceLiveMessage):
    """
    WebSocket metrics message schema for Live Voice.

    Used for sending real-time performance and quality metrics
    during Live Voice sessions.
    """

    type: str = Field(
        default="metrics",
        description="Message type - always 'metrics' for metrics messages",
        json_schema_extra={"example": "metrics"},
    )

    latency_metrics: dict[str, float] | None = Field(
        None,
        description="Latency measurements in milliseconds",
        json_schema_extra={
            "example": {
                "audio_to_text": 150.5,
                "text_to_response": 200.3,
                "response_to_audio": 180.7,
                "end_to_end": 531.5,
            }
        },
    )

    quality_metrics: dict[str, float] | None = Field(
        None,
        description="Quality measurements",
        json_schema_extra={
            "example": {
                "speech_recognition_confidence": 0.95,
                "audio_quality_score": 0.88,
                "voice_activity_accuracy": 0.92,
            }
        },
    )

    resource_metrics: dict[str, float] | None = Field(
        None,
        description="Resource utilization metrics",
        json_schema_extra={
            "example": {
                "cpu_usage_percent": 25.5,
                "memory_usage_mb": 128.3,
                "network_throughput_kbps": 64.2,
            }
        },
    )

    session_stats: dict[str, Any] | None = Field(
        None,
        description="Session statistics",
        json_schema_extra={
            "example": {
                "total_messages": 10,
                "audio_bytes_processed": 102400,
                "speaking_time_seconds": 45.2,
                "listening_time_seconds": 120.8,
                "interruption_count": 2,
            }
        },
    )


class VoiceLiveConfigurationMessage(VoiceLiveMessage):
    """
    WebSocket configuration message schema for Live Voice.

    Used for dynamic configuration updates during active Live Voice sessions.
    """

    type: str = Field(
        default="configuration",
        description="Message type - always 'configuration' for configuration messages",
        json_schema_extra={"example": "configuration"},
    )

    configuration_type: str = Field(
        ...,
        description="Type of configuration being updated",
        json_schema_extra={
            "example": "audio",
            "enum": ["audio", "model", "session", "voice"],
        },
    )

    configuration_data: dict[str, Any] = Field(
        ...,
        description="Configuration data",
        json_schema_extra={
            "example": {
                "sample_rate": 24000,
                "vad_sensitivity": 0.7,
                "noise_reduction": True,
            }
        },
    )

    apply_immediately: bool = Field(
        default=True,
        description="Whether to apply the configuration immediately",
        json_schema_extra={"example": True},
    )


# Union type for all Live Voice message types
VoiceLiveWebSocketMessage = Union[
    VoiceLiveAudioMessage,
    VoiceLiveTextMessage,
    VoiceLiveControlMessage,
    VoiceLiveStatusMessage,
    VoiceLiveErrorMessage,
    VoiceLiveMetricsMessage,
    VoiceLiveConfigurationMessage,
]

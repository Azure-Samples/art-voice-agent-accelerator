"""
Media API Schemas
================

Pydantic schemas for media streaming, transcription, and audio processing endpoints.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaSessionRequest(BaseModel):
    """Request schema for starting a media session."""

    call_connection_id: str = Field(
        ...,
        description="ACS call connection identifier",
        json_schema_extra={"example": "call_12345"},
    )
    sample_rate: int | None = Field(
        16000,
        description="Audio sample rate in Hz",
        json_schema_extra={"example": 16000},
    )
    channels: int | None = Field(
        1, description="Number of audio channels", json_schema_extra={"example": 1}
    )
    audio_format: str | None = Field(
        "pcm_16",
        description="Audio format (pcm_16, pcm_24, opus, etc.)",
        json_schema_extra={"example": "pcm_16"},
    )
    chunk_size: int | None = Field(
        1024,
        description="Audio chunk size in bytes",
        json_schema_extra={"example": 1024},
    )
    enable_transcription: bool | None = Field(
        True,
        description="Enable real-time transcription",
        json_schema_extra={"example": True},
    )
    enable_vad: bool | None = Field(
        True,
        description="Enable voice activity detection",
        json_schema_extra={"example": True},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "call_connection_id": "call_12345",
                "sample_rate": 16000,
                "channels": 1,
                "audio_format": "pcm_16",
                "chunk_size": 1024,
                "enable_transcription": True,
                "enable_vad": True,
            }
        }
    )


class MediaSessionResponse(BaseModel):
    """Response schema for media session creation."""

    session_id: str = Field(
        ...,
        description="Unique media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    websocket_url: str = Field(
        ...,
        description="WebSocket URL for audio streaming",
        json_schema_extra={"example": "wss://api.example.com/v1/media/stream/media_session_123456"},
    )
    status: str = Field(..., description="Session status", json_schema_extra={"example": "active"})
    created_at: str = Field(
        ...,
        description="Session creation timestamp",
        json_schema_extra={"example": "2025-08-10T13:45:00Z"},
    )
    configuration: dict[str, Any] = Field(
        ...,
        description="Session configuration settings",
        json_schema_extra={
            "example": {
                "sample_rate": 16000,
                "channels": 1,
                "format": "pcm_16",
                "chunk_size": 1024,
            }
        },
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "websocket_url": "wss://api.example.com/v1/media/stream/media_session_123456",
                "status": "active",
                "created_at": "2025-08-10T13:45:00Z",
                "configuration": {
                    "sample_rate": 16000,
                    "channels": 1,
                    "format": "pcm_16",
                    "chunk_size": 1024,
                },
            }
        }
    )


class TranscriptionRequest(BaseModel):
    """Request schema for starting transcription."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    language: str | None = Field(
        "en-US",
        description="Transcription language code",
        json_schema_extra={"example": "en-US"},
    )
    confidence_threshold: float | None = Field(
        0.5,
        description="Minimum confidence threshold for results",
        json_schema_extra={"example": 0.5},
        ge=0.0,
        le=1.0,
    )
    enable_interim_results: bool | None = Field(
        True,
        description="Enable interim (partial) transcription results",
        json_schema_extra={"example": True},
    )
    enable_speaker_diarization: bool | None = Field(
        False,
        description="Enable speaker identification",
        json_schema_extra={"example": False},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "language": "en-US",
                "confidence_threshold": 0.5,
                "enable_interim_results": True,
                "enable_speaker_diarization": False,
            }
        }
    )


class TranscriptionResponse(BaseModel):
    """Response schema for transcription service."""

    transcription_id: str = Field(
        ...,
        description="Unique transcription identifier",
        json_schema_extra={"example": "transcription_media_session_123456"},
    )
    session_id: str = Field(
        ...,
        description="Associated media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    status: str = Field(
        ...,
        description="Transcription service status",
        json_schema_extra={"example": "active"},
    )
    language: str = Field(
        ...,
        description="Transcription language",
        json_schema_extra={"example": "en-US"},
    )
    confidence_threshold: float = Field(
        ...,
        description="Confidence threshold setting",
        json_schema_extra={"example": 0.5},
    )
    started_at: str = Field(
        ...,
        description="Transcription start timestamp",
        json_schema_extra={"example": "2025-08-10T13:45:00Z"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transcription_id": "transcription_media_session_123456",
                "session_id": "media_session_123456",
                "status": "active",
                "language": "en-US",
                "confidence_threshold": 0.5,
                "started_at": "2025-08-10T13:45:00Z",
            }
        }
    )


class AudioStreamStatus(BaseModel):
    """Schema for audio stream status information."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    is_active: bool = Field(
        ...,
        description="Whether the stream is currently active",
        json_schema_extra={"example": True},
    )
    connected_at: str = Field(
        ...,
        description="Stream connection timestamp",
        json_schema_extra={"example": "2025-08-10T13:45:00Z"},
    )
    last_activity: str = Field(
        ...,
        description="Last activity timestamp",
        json_schema_extra={"example": "2025-08-10T13:47:30Z"},
    )
    total_audio_chunks: int = Field(
        ...,
        description="Total audio chunks processed",
        json_schema_extra={"example": 1250},
    )
    total_duration_seconds: float = Field(
        ...,
        description="Total audio duration in seconds",
        json_schema_extra={"example": 125.0},
    )
    is_speaking: bool = Field(
        ...,
        description="Current voice activity status",
        json_schema_extra={"example": False},
    )
    voice_activity_confidence: float = Field(
        ...,
        description="Voice activity detection confidence",
        json_schema_extra={"example": 0.15},
        ge=0.0,
        le=1.0,
    )
    transcription_enabled: bool = Field(
        ...,
        description="Whether transcription is enabled",
        json_schema_extra={"example": True},
    )
    last_transcription: str | None = Field(
        None,
        description="Last transcription result",
        json_schema_extra={"example": "Hello, how can I help you today?"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "is_active": True,
                "connected_at": "2025-08-10T13:45:00Z",
                "last_activity": "2025-08-10T13:47:30Z",
                "total_audio_chunks": 1250,
                "total_duration_seconds": 125.0,
                "is_speaking": False,
                "voice_activity_confidence": 0.15,
                "transcription_enabled": True,
                "last_transcription": "Hello, how can I help you today?",
            }
        }
    )


class VoiceActivityResponse(BaseModel):
    """Schema for voice activity detection results."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    is_speaking: bool = Field(
        ...,
        description="Whether speech is currently detected",
        json_schema_extra={"example": False},
    )
    confidence: float = Field(
        ...,
        description="Voice activity confidence score",
        json_schema_extra={"example": 0.15},
        ge=0.0,
        le=1.0,
    )
    last_speech_detected: str | None = Field(
        None,
        description="Timestamp of last speech detection",
        json_schema_extra={"example": "2025-08-10T13:47:25Z"},
    )
    speech_duration_seconds: float | None = Field(
        None,
        description="Duration of last speech segment",
        json_schema_extra={"example": 2.3},
    )
    silence_duration_seconds: float | None = Field(
        None,
        description="Duration of current silence",
        json_schema_extra={"example": 5.2},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "is_speaking": False,
                "confidence": 0.15,
                "last_speech_detected": "2025-08-10T13:47:25Z",
                "speech_duration_seconds": 2.3,
                "silence_duration_seconds": 5.2,
            }
        }
    )


class MediaMetricsResponse(BaseModel):
    """Schema for media processing metrics."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    total_audio_chunks: int = Field(
        ...,
        description="Total audio chunks processed",
        json_schema_extra={"example": 1250},
    )
    total_duration_seconds: float = Field(
        ...,
        description="Total audio duration processed",
        json_schema_extra={"example": 125.0},
    )
    average_latency_ms: float = Field(
        ...,
        description="Average processing latency in milliseconds",
        json_schema_extra={"example": 45.2},
    )
    transcription_accuracy: float | None = Field(
        None,
        description="Transcription accuracy score",
        json_schema_extra={"example": 0.94},
        ge=0.0,
        le=1.0,
    )
    voice_activity_percentage: float | None = Field(
        None,
        description="Percentage of time with voice activity",
        json_schema_extra={"example": 45.6},
        ge=0.0,
        le=100.0,
    )
    processing_errors: int = Field(
        ..., description="Number of processing errors", json_schema_extra={"example": 0}
    )
    last_updated: str = Field(
        ...,
        description="Metrics last updated timestamp",
        json_schema_extra={"example": "2025-08-10T13:47:30Z"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "total_audio_chunks": 1250,
                "total_duration_seconds": 125.0,
                "average_latency_ms": 45.2,
                "transcription_accuracy": 0.94,
                "voice_activity_percentage": 45.6,
                "processing_errors": 0,
                "last_updated": "2025-08-10T13:47:30Z",
            }
        }
    )


class AudioConfigRequest(BaseModel):
    """Request schema for audio configuration updates."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    sample_rate: int | None = Field(
        None,
        description="Audio sample rate in Hz",
        json_schema_extra={"example": 16000},
    )
    channels: int | None = Field(
        None, description="Number of audio channels", json_schema_extra={"example": 1}
    )
    format: str | None = Field(
        None, description="Audio format", json_schema_extra={"example": "pcm_16"}
    )
    noise_reduction_enabled: bool | None = Field(
        None, description="Enable noise reduction", json_schema_extra={"example": True}
    )
    echo_cancellation_enabled: bool | None = Field(
        None,
        description="Enable echo cancellation",
        json_schema_extra={"example": True},
    )
    auto_gain_control_enabled: bool | None = Field(
        None,
        description="Enable automatic gain control",
        json_schema_extra={"example": False},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "sample_rate": 16000,
                "channels": 1,
                "format": "pcm_16",
                "noise_reduction_enabled": True,
                "echo_cancellation_enabled": True,
                "auto_gain_control_enabled": False,
            }
        }
    )


class AudioConfigResponse(BaseModel):
    """Response schema for audio configuration updates."""

    session_id: str = Field(
        ...,
        description="Media session identifier",
        json_schema_extra={"example": "media_session_123456"},
    )
    sample_rate: int = Field(
        ...,
        description="Current audio sample rate",
        json_schema_extra={"example": 16000},
    )
    channels: int = Field(
        ...,
        description="Current number of audio channels",
        json_schema_extra={"example": 1},
    )
    format: str = Field(
        ..., description="Current audio format", json_schema_extra={"example": "pcm_16"}
    )
    noise_reduction_enabled: bool = Field(
        ..., description="Noise reduction status", json_schema_extra={"example": True}
    )
    echo_cancellation_enabled: bool = Field(
        ..., description="Echo cancellation status", json_schema_extra={"example": True}
    )
    auto_gain_control_enabled: bool = Field(
        ...,
        description="Auto gain control status",
        json_schema_extra={"example": False},
    )
    applied_at: str = Field(
        ...,
        description="Configuration applied timestamp",
        json_schema_extra={"example": "2025-08-10T13:47:30Z"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "media_session_123456",
                "sample_rate": 16000,
                "channels": 1,
                "format": "pcm_16",
                "noise_reduction_enabled": True,
                "echo_cancellation_enabled": True,
                "auto_gain_control_enabled": False,
                "applied_at": "2025-08-10T13:47:30Z",
            }
        }
    )

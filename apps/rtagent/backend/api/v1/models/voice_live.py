"""
Live Voice Models
=================

Pydantic models for Live Voice session management and Azure AI Speech integration.

This module provides data models for:
- Live Voice session state and configuration
- Azure AI Speech client integration
- Audio processing configuration
- Session metrics and monitoring
- WebSocket connection management
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from uuid import UUID
import uuid

from pydantic import BaseModel, Field, ConfigDict


class VoiceLiveSessionStatus(str, Enum):
    """Enumeration of possible Live Voice session statuses."""

    INITIALIZING = "initializing"
    CONNECTED = "connected"
    PROCESSING = "processing"
    PAUSED = "paused"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class AudioFormat(str, Enum):
    """Supported audio formats for Live Voice sessions."""

    PCM = "pcm"
    OPUS = "opus"
    MP3 = "mp3"
    WAV = "wav"


class VoiceActivityDetectionMode(str, Enum):
    """Voice Activity Detection modes for Live Voice sessions."""

    AUTO = "auto"
    MANUAL = "manual"
    DISABLED = "disabled"


class VoiceLiveAudioConfig(BaseModel):
    """Configuration model for Live Voice audio processing."""

    model_config = ConfigDict(validate_assignment=True)

    # Audio Format Settings (Azure Voice Live API supports 16000 and 24000 Hz)
    sample_rate: int = Field(
        default=24000,
        description="Audio sample rate in Hz",
        json_schema_extra={"enum": [16000, 24000]},
    )
    channels: int = Field(default=1, description="Number of audio channels", ge=1, le=2)
    bit_depth: int = Field(default=16, description="Audio bit depth", ge=8, le=32)
    format: AudioFormat = Field(default=AudioFormat.PCM, description="Audio format")
    language: str = Field(default="en-US", description="Audio language code")

    # Voice Activity Detection (Azure Voice Live API specific)
    vad_enabled: bool = Field(
        default=True, description="Enable voice activity detection"
    )
    vad_mode: VoiceActivityDetectionMode = Field(
        default=VoiceActivityDetectionMode.AUTO, description="VAD mode"
    )
    vad_sensitivity: float = Field(
        default=0.3, description="VAD threshold (0.0-1.0)", ge=0.0, le=1.0
    )

    # Azure AI Speech Enhancement Features
    noise_reduction: bool = Field(
        default=True, description="Enable Azure deep noise suppression"
    )
    echo_cancellation: bool = Field(
        default=True, description="Enable server-side echo cancellation"
    )
    automatic_gain_control: bool = Field(
        default=False, description="Enable automatic gain control"
    )

    # Azure Voice Live API specific audio settings
    input_audio_noise_reduction_type: str = Field(
        default="azure_deep_noise_suppression", description="Azure noise reduction type"
    )
    input_audio_echo_cancellation_type: str = Field(
        default="server_echo_cancellation", description="Azure echo cancellation type"
    )


class VoiceLiveModelConfig(BaseModel):
    """Configuration model for Live Voice AI model settings."""

    model_config = ConfigDict(validate_assignment=True)

    model_name: str = Field(default="gpt-4o", description="AI model name")
    deployment_name: Optional[str] = Field(None, description="Azure deployment name")
    temperature: float = Field(
        default=0.7, description="Model temperature", ge=0.0, le=2.0
    )
    max_tokens: int = Field(
        default=2000, description="Maximum tokens per response", ge=1, le=4000
    )

    # Voice Settings (Updated for Azure Voice Live API)
    voice_name: str = Field(
        default="en-US-Ava:DragonHDLatestNeural", description="Azure neural voice name"
    )
    voice_type: str = Field(default="azure-standard", description="Azure voice type")
    voice_style: Optional[str] = Field(None, description="Voice style")
    speaking_rate: float = Field(
        default=1.0, description="Speaking rate", ge=0.5, le=2.0
    )
    voice_temperature: float = Field(
        default=0.8, description="Voice temperature for HD voices", ge=0.0, le=1.0
    )

    # System Configuration
    system_instructions: Optional[str] = Field(
        default="You are a helpful AI assistant responding in natural, engaging language.",
        description="System instructions for the AI",
    )
    context_window: int = Field(
        default=4000, description="Context window size", ge=1000, le=8000
    )

    # Azure Voice Live API specific settings
    api_version: str = Field(
        default="2025-05-01-preview", description="Azure Voice Live API version"
    )
    turn_detection_type: str = Field(
        default="azure_semantic_vad", description="Turn detection type"
    )
    vad_threshold: float = Field(
        default=0.3, description="VAD threshold", ge=0.0, le=1.0
    )
    prefix_padding_ms: int = Field(
        default=200, description="Prefix padding in milliseconds", ge=0
    )
    silence_duration_ms: int = Field(
        default=200, description="Silence duration in milliseconds", ge=0
    )
    remove_filler_words: bool = Field(default=False, description="Remove filler words")

    # End of utterance detection
    end_of_utterance_enabled: bool = Field(
        default=True, description="Enable end of utterance detection"
    )
    end_of_utterance_model: str = Field(
        default="semantic_detection_v1", description="End of utterance model"
    )
    end_of_utterance_threshold: float = Field(
        default=0.01, description="End of utterance threshold", ge=0.0, le=1.0
    )
    end_of_utterance_timeout: int = Field(
        default=2, description="End of utterance timeout in seconds", ge=1
    )


class VoiceLiveConnectionState(BaseModel):
    """Model for tracking Live Voice WebSocket connection state."""

    model_config = ConfigDict(validate_assignment=True)

    session_id: str = Field(..., description="Session identifier")
    websocket_id: str = Field(..., description="WebSocket connection identifier")
    connected_at: datetime = Field(
        default_factory=datetime.utcnow, description="Connection timestamp"
    )
    last_activity_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last activity timestamp"
    )

    # Connection Statistics
    messages_sent: int = Field(default=0, description="Number of messages sent", ge=0)
    messages_received: int = Field(
        default=0, description="Number of messages received", ge=0
    )
    bytes_sent: int = Field(default=0, description="Total bytes sent", ge=0)
    bytes_received: int = Field(default=0, description="Total bytes received", ge=0)

    # Error Tracking
    connection_errors: int = Field(
        default=0, description="Connection error count", ge=0
    )
    protocol_errors: int = Field(default=0, description="Protocol error count", ge=0)

    def record_message_sent(self, byte_count: int = 0) -> None:
        """Record a message sent."""
        self.messages_sent += 1
        self.bytes_sent += byte_count
        self.last_activity_at = datetime.utcnow()

    def record_message_received(self, byte_count: int = 0) -> None:
        """Record a message received."""
        self.messages_received += 1
        self.bytes_received += byte_count
        self.last_activity_at = datetime.utcnow()

    def record_connection_error(self) -> None:
        """Record a connection error."""
        self.connection_errors += 1
        self.last_activity_at = datetime.utcnow()

    def record_protocol_error(self) -> None:
        """Record a protocol error."""
        self.protocol_errors += 1
        self.last_activity_at = datetime.utcnow()


class VoiceLiveMetrics(BaseModel):
    """Model for Live Voice session performance metrics."""

    model_config = ConfigDict(validate_assignment=True)

    session_id: str = Field(..., description="Session identifier")
    measurement_start: datetime = Field(
        default_factory=datetime.utcnow, description="Measurement start time"
    )
    last_update: datetime = Field(
        default_factory=datetime.utcnow, description="Last metrics update"
    )

    # Latency Metrics (in milliseconds)
    audio_to_text_latency: Optional[float] = Field(
        None, description="Audio to text latency", ge=0.0
    )
    text_to_response_latency: Optional[float] = Field(
        None, description="Text to response latency", ge=0.0
    )
    response_to_audio_latency: Optional[float] = Field(
        None, description="Response to audio latency", ge=0.0
    )
    end_to_end_latency: Optional[float] = Field(
        None, description="End-to-end latency", ge=0.0
    )

    # Quality Metrics
    speech_recognition_confidence: Optional[float] = Field(
        None, description="Speech recognition confidence", ge=0.0, le=1.0
    )
    audio_quality_score: Optional[float] = Field(
        None, description="Audio quality score", ge=0.0, le=1.0
    )
    voice_activity_accuracy: Optional[float] = Field(
        None, description="VAD accuracy", ge=0.0, le=1.0
    )

    # Resource Metrics
    cpu_usage_percent: Optional[float] = Field(
        None, description="CPU usage percentage", ge=0.0, le=100.0
    )
    memory_usage_mb: Optional[float] = Field(
        None, description="Memory usage in MB", ge=0.0
    )
    network_throughput_kbps: Optional[float] = Field(
        None, description="Network throughput in kbps", ge=0.0
    )

    def update_latency(self, metric_type: str, value: float) -> None:
        """Update a latency metric."""
        if hasattr(self, f"{metric_type}_latency"):
            setattr(self, f"{metric_type}_latency", value)
            self.last_update = datetime.utcnow()

    def update_quality(self, metric_type: str, value: float) -> None:
        """Update a quality metric."""
        if hasattr(self, metric_type):
            setattr(self, metric_type, value)
            self.last_update = datetime.utcnow()


class VoiceLiveSession(BaseModel):
    """Complete Live Voice session model."""

    model_config = ConfigDict(validate_assignment=True)

    session_id: str = Field(..., description="Unique session identifier")
    status: VoiceLiveSessionStatus = Field(
        default=VoiceLiveSessionStatus.INITIALIZING, description="Session status"
    )
    status_message: Optional[str] = Field(None, description="Status message")

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Session creation time"
    )
    connection_established_at: Optional[datetime] = Field(
        None, description="Connection establishment time"
    )
    last_activity_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last activity time"
    )
    disconnected_at: Optional[datetime] = Field(None, description="Disconnection time")

    # Configuration
    audio_config: VoiceLiveAudioConfig = Field(
        default_factory=VoiceLiveAudioConfig, description="Audio configuration"
    )
    model_configuration: VoiceLiveModelConfig = Field(
        default_factory=VoiceLiveModelConfig, description="Model configuration"
    )

    # Connection State
    websocket_connected: bool = Field(
        default=False, description="WebSocket connection status"
    )
    azure_speech_connected: bool = Field(
        default=False, description="Azure Speech connection status"
    )

    # Session Statistics
    total_messages: int = Field(default=0, description="Total messages processed", ge=0)
    audio_bytes_processed: int = Field(
        default=0, description="Total audio bytes processed", ge=0
    )
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="Conversation history"
    )

    # Error Tracking
    error_count: int = Field(default=0, description="Total error count", ge=0)
    last_error: Optional[str] = Field(None, description="Last error message")
    last_error_at: Optional[datetime] = Field(None, description="Last error timestamp")

    # Performance Metrics
    average_response_time_ms: float = Field(
        default=0.0, description="Average response time", ge=0.0
    )

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity_at = datetime.utcnow()

    def add_conversation_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a message to the conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self.conversation_history.append(message)
        self.total_messages += 1
        self.update_activity()

    def add_audio_bytes(self, byte_count: int) -> None:
        """Add processed audio bytes count."""
        self.audio_bytes_processed += byte_count
        self.update_activity()

    def record_error(self, error_message: str) -> None:
        """Record an error in the session."""
        self.error_count += 1
        self.last_error = error_message
        self.last_error_at = datetime.utcnow()
        self.status = VoiceLiveSessionStatus.ERROR
        self.status_message = error_message
        self.update_activity()

    def set_status(
        self, status: VoiceLiveSessionStatus, message: Optional[str] = None
    ) -> None:
        """Update session status."""
        self.status = status
        if message:
            self.status_message = message
        self.update_activity()

    def get_session_duration_seconds(self) -> float:
        """Get session duration in seconds."""
        if self.connection_established_at:
            end_time = self.disconnected_at or datetime.utcnow()
            return (end_time - self.connection_established_at).total_seconds()
        return 0.0

    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get a summary of the conversation."""
        user_messages = [
            msg for msg in self.conversation_history if msg["role"] == "user"
        ]
        assistant_messages = [
            msg for msg in self.conversation_history if msg["role"] == "assistant"
        ]

        return {
            "total_messages": len(self.conversation_history),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "duration_seconds": self.get_session_duration_seconds(),
            "audio_mb_processed": round(self.audio_bytes_processed / 1024 / 1024, 2),
            "average_response_time_ms": self.average_response_time_ms,
            "error_rate": self.error_count / max(self.total_messages, 1),
        }

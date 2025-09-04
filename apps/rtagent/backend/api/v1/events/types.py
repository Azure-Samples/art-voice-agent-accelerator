"""
V1 Event Types
==============

Simple type definitions for V1 event processing inspired by Azure's Event Processor pattern.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from azure.core.messaging import CloudEvent
from enum import Enum
from datetime import datetime

from src.stateful.state_managment import MemoManager


@dataclass
class CallEventContext:
    """
    Simplified context for call event processing.

    Inspired by Azure's Event Processor pattern but simplified for V1 needs.
    Contains only essential data for call event handling.
    """

    event: CloudEvent
    call_connection_id: str
    event_type: str
    memo_manager: Optional[MemoManager] = None
    redis_mgr: Optional[Any] = None
    acs_caller: Optional[Any] = None
    clients: Optional[list] = None
    app_state: Optional[Any] = None  # For accessing ConnectionManager

    def get_event_data(self) -> Dict[str, Any]:
        """
        Safely extract event data as dictionary.

        :return: Event data as dictionary
        :rtype: Dict[str, Any]
        """
        try:
            data = self.event.data
            if isinstance(data, dict):
                return data
            elif isinstance(data, str):
                import json

                return json.loads(data)
            elif isinstance(data, bytes):
                import json

                return json.loads(data.decode("utf-8"))
            elif hasattr(data, "__dict__"):
                return data.__dict__
            else:
                return {}
        except Exception:
            return {}

    def get_event_field(self, field_name: str, default: Any = None) -> Any:
        """
        Safely get a field from event data.

        :param field_name: Name of the field to extract from event data
        :type field_name: str
        :param default: Default value to return if field not found
        :type default: Any
        :return: Field value or default if not found
        :rtype: Any
        """
        return self.get_event_data().get(field_name, default)


@runtime_checkable
class CallEventHandler(Protocol):
    """Protocol for call event handlers following Azure Event Processor pattern."""

    async def __call__(self, context: CallEventContext) -> None:
        """
        Handle a call event with the given context.

        :param context: Call event context containing event details and dependencies
        :type context: CallEventContext
        """
        ...


class VoiceLiveEventPriority(str, Enum):
    """Priority levels for Live Voice events."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class VoiceLiveEventContext(CallEventContext):
    """
    Extended context for Live Voice event processing.

    Extends the base CallEventContext with Live Voice specific data
    and provides access to Live Voice session state and resources.
    """

    # Live Voice specific identifiers
    session_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    priority: VoiceLiveEventPriority = VoiceLiveEventPriority.NORMAL

    # Live Voice specific resources
    voice_live_session: Optional[Any] = None
    connection_state: Optional[Any] = None
    websocket: Optional[Any] = None
    azure_speech_client: Optional[Any] = None

    # Event data specific to Live Voice
    voice_live_event_data: Optional[Dict[str, Any]] = None
    error_details: Optional[Dict[str, Any]] = None
    metrics_data: Optional[Dict[str, Any]] = None

    # Additional dependencies for Live Voice
    orchestrator: Optional[Any] = None

    def __post_init__(self):
        """Initialize Live Voice event data if not provided."""
        if self.voice_live_event_data is None:
            self.voice_live_event_data = {}

    def get_voice_live_field(self, field_name: str, default: Any = None) -> Any:
        """
        Get a field from Live Voice event data.

        :param field_name: Name of the field to retrieve
        :param default: Default value if field not found
        :return: Field value or default
        """
        return self.voice_live_event_data.get(field_name, default)

    def set_voice_live_field(self, field_name: str, value: Any) -> None:
        """
        Set a field in Live Voice event data.

        :param field_name: Name of the field to set
        :param value: Value to set
        """
        self.voice_live_event_data[field_name] = value

    def has_error(self) -> bool:
        """Check if the event context contains error information."""
        return self.error_details is not None and len(self.error_details) > 0

    def add_error_detail(self, key: str, value: Any) -> None:
        """Add error detail information."""
        if self.error_details is None:
            self.error_details = {}
        self.error_details[key] = value

    def add_metric(self, metric_name: str, value: Any) -> None:
        """Add metric information."""
        if self.metrics_data is None:
            self.metrics_data = {}
        self.metrics_data[metric_name] = value


@runtime_checkable
class VoiceLiveEventHandler(Protocol):
    """Protocol for Live Voice event handlers."""

    async def __call__(self, context: VoiceLiveEventContext) -> None:
        """
        Handle a Live Voice event with the given context.

        :param context: Live Voice event context containing event details and resources
        """
        ...


# Standard ACS event types
class ACSEventTypes:
    """Standard Azure Communication Services event types."""

    # Call Management
    CALL_CONNECTED = "Microsoft.Communication.CallConnected"
    CALL_DISCONNECTED = "Microsoft.Communication.CallDisconnected"
    CALL_TRANSFER_ACCEPTED = "Microsoft.Communication.CallTransferAccepted"
    CALL_TRANSFER_FAILED = "Microsoft.Communication.CallTransferFailed"
    CREATE_CALL_FAILED = "Microsoft.Communication.CreateCallFailed"
    ANSWER_CALL_FAILED = "Microsoft.Communication.AnswerCallFailed"

    # Participants
    PARTICIPANTS_UPDATED = "Microsoft.Communication.ParticipantsUpdated"

    # DTMF
    DTMF_TONE_RECEIVED = "Microsoft.Communication.ContinuousDtmfRecognitionToneReceived"
    DTMF_TONE_FAILED = "Microsoft.Communication.ContinuousDtmfRecognitionToneFailed"
    DTMF_TONE_STOPPED = "Microsoft.Communication.ContinuousDtmfRecognitionStopped"

    # Media
    PLAY_COMPLETED = "Microsoft.Communication.PlayCompleted"
    PLAY_FAILED = "Microsoft.Communication.PlayFailed"
    PLAY_CANCELED = "Microsoft.Communication.PlayCanceled"

    # Recognition
    RECOGNIZE_COMPLETED = "Microsoft.Communication.RecognizeCompleted"
    RECOGNIZE_FAILED = "Microsoft.Communication.RecognizeFailed"
    RECOGNIZE_CANCELED = "Microsoft.Communication.RecognizeCanceled"


# Custom V1 API event types for lifecycle management
class V1EventTypes:
    """Custom V1 API event types for call lifecycle management."""

    # API-initiated events
    CALL_INITIATED = "V1.Call.Initiated"
    INBOUND_CALL_RECEIVED = "V1.Call.InboundReceived"
    CALL_ANSWERED = "V1.Call.Answered"
    WEBHOOK_EVENTS = "V1.Webhook.Events"

    # State management events
    CALL_STATE_UPDATED = "V1.Call.StateUpdated"
    CALL_CLEANUP_REQUESTED = "V1.Call.CleanupRequested"

    # DTMF management events
    DTMF_RECOGNITION_START_REQUESTED = "V1.DTMF.RecognitionStartRequested"

    # Live Voice WebSocket events
    LIVE_VOICE_SESSION_INITIALIZED = "V1.VoiceLive.Session.Initialized"
    LIVE_VOICE_SESSION_CONNECTED = "V1.VoiceLive.Session.Connected"
    LIVE_VOICE_SESSION_DISCONNECTED = "V1.VoiceLive.Session.Disconnected"
    LIVE_VOICE_SESSION_ERROR = "V1.VoiceLive.Session.Error"
    LIVE_VOICE_SESSION_TIMEOUT = "V1.VoiceLive.Session.Timeout"

    # Azure AI Speech Integration
    LIVE_VOICE_AZURE_SPEECH_CONNECTED = "V1.VoiceLive.AzureSpeech.Connected"
    LIVE_VOICE_AZURE_SPEECH_DISCONNECTED = "V1.VoiceLive.AzureSpeech.Disconnected"
    LIVE_VOICE_AZURE_SPEECH_ERROR = "V1.VoiceLive.AzureSpeech.Error"

    # Audio Processing
    LIVE_VOICE_AUDIO_STREAM_STARTED = "V1.VoiceLive.Audio.StreamStarted"
    LIVE_VOICE_AUDIO_STREAM_STOPPED = "V1.VoiceLive.Audio.StreamStopped"
    LIVE_VOICE_AUDIO_DATA_RECEIVED = "V1.VoiceLive.Audio.DataReceived"
    LIVE_VOICE_AUDIO_PROCESSING_ERROR = "V1.VoiceLive.Audio.ProcessingError"

    # Voice Activity Detection
    LIVE_VOICE_VAD_SPEECH_STARTED = "V1.VoiceLive.VAD.SpeechStarted"
    LIVE_VOICE_VAD_SPEECH_ENDED = "V1.VoiceLive.VAD.SpeechEnded"
    LIVE_VOICE_VAD_SILENCE_DETECTED = "V1.VoiceLive.VAD.SilenceDetected"

    # Text Processing
    LIVE_VOICE_TEXT_TRANSCRIPTION_RECEIVED = "V1.VoiceLive.Text.TranscriptionReceived"
    LIVE_VOICE_TEXT_RESPONSE_GENERATED = "V1.VoiceLive.Text.ResponseGenerated"
    LIVE_VOICE_TEXT_SYNTHESIS_STARTED = "V1.VoiceLive.Text.SynthesisStarted"
    LIVE_VOICE_TEXT_SYNTHESIS_COMPLETED = "V1.VoiceLive.Text.SynthesisCompleted"

    # Configuration
    LIVE_VOICE_CONFIGURATION_UPDATED = "V1.VoiceLive.Configuration.Updated"
    LIVE_VOICE_AUDIO_CONFIG_CHANGED = "V1.VoiceLive.Audio.ConfigChanged"
    LIVE_VOICE_MODEL_CONFIG_CHANGED = "V1.VoiceLive.Model.ConfigChanged"

    # Performance Monitoring
    LIVE_VOICE_METRICS_UPDATED = "V1.VoiceLive.Metrics.Updated"
    LIVE_VOICE_PERFORMANCE_THRESHOLD_EXCEEDED = (
        "V1.VoiceLive.Performance.ThresholdExceeded"
    )
    LIVE_VOICE_QUALITY_DEGRADED = "V1.VoiceLive.Quality.Degraded"

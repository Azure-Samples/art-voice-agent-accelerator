"""
Pydantic schemas for API request/response models.

This package contains all Pydantic schema definitions for:
- API request and response models
- Data validation and serialization
- OpenAPI documentation generation
"""

from .call import (
    CallHangupResponse,
    CallInitiateRequest,
    CallInitiateResponse,
    CallListResponse,
    CallStatusResponse,
    CallUpdateRequest,
)
from .event import (
    EventHandlerInfo,
    EventListResponse,
    EventMetricsResponse,
    EventSystemStatus,
    ProcessEventRequest,
    ProcessEventResponse,
)
from .health import (
    HealthResponse,
    ReadinessResponse,
    ServiceCheck,
)
from .media import (
    AudioConfigRequest,
    AudioConfigResponse,
    AudioStreamStatus,
    MediaMetricsResponse,
    MediaSessionRequest,
    MediaSessionResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    VoiceActivityResponse,
)
from .participant import (
    ParticipantInviteRequest,
    ParticipantInviteResponse,
    ParticipantListResponse,
    ParticipantResponse,
    ParticipantUpdateRequest,
)
from .voice_live import (
    VoiceLiveConfigRequest,
    VoiceLiveControlMessage,
    VoiceLiveErrorMessage,
    VoiceLiveMetricsMessage,
    VoiceLiveSessionResponse,
    VoiceLiveStatusMessage,
    VoiceLiveStatusResponse,
    VoiceLiveTextMessage,
)
from .webhook import (
    ACSWebhookEvent,
    MediaWebhookEvent,
    WebhookEvent,
    WebhookResponse,
)

__all__ = [
    # Call schemas
    "CallInitiateRequest",
    "CallInitiateResponse",
    "CallStatusResponse",
    "CallHangupResponse",
    "CallListResponse",
    "CallUpdateRequest",
    # Event schemas
    "EventMetricsResponse",
    "EventHandlerInfo",
    "EventSystemStatus",
    "ProcessEventRequest",
    "ProcessEventResponse",
    "EventListResponse",
    # Health schemas
    "HealthResponse",
    "ServiceCheck",
    "ReadinessResponse",
    # Media schemas
    "MediaSessionRequest",
    "MediaSessionResponse",
    "TranscriptionRequest",
    "TranscriptionResponse",
    "AudioStreamStatus",
    "VoiceActivityResponse",
    "MediaMetricsResponse",
    "AudioConfigRequest",
    "AudioConfigResponse",
    # Participant schemas
    "ParticipantResponse",
    "ParticipantUpdateRequest",
    "ParticipantListResponse",
    "ParticipantInviteRequest",
    "ParticipantInviteResponse",
    # Webhook schemas
    "WebhookEvent",
    "WebhookResponse",
    "ACSWebhookEvent",
    "MediaWebhookEvent",
    # Voice Live schemas
    "VoiceLiveStatusResponse",
    "VoiceLiveSessionResponse",
    "VoiceLiveConfigRequest",
    "VoiceLiveStatusMessage",
    "VoiceLiveErrorMessage",
    "VoiceLiveTextMessage",
    "VoiceLiveMetricsMessage",
    "VoiceLiveControlMessage",
]

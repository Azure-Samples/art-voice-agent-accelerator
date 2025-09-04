"""
Pydantic schemas for API request/response models.

This package contains all Pydantic schema definitions for:
- API request and response models
- Data validation and serialization
- OpenAPI documentation generation
"""

from .call import (
    CallInitiateRequest,
    CallInitiateResponse,
    CallStatusResponse,
    CallHangupResponse,
    CallListResponse,
    CallUpdateRequest,
)
from .event import (
    EventMetricsResponse,
    EventHandlerInfo,
    EventSystemStatus,
    ProcessEventRequest,
    ProcessEventResponse,
    EventListResponse,
)
from .health import (
    HealthResponse,
    ServiceCheck,
    ReadinessResponse,
)
from .media import (
    MediaSessionRequest,
    MediaSessionResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    AudioStreamStatus,
    VoiceActivityResponse,
    MediaMetricsResponse,
    AudioConfigRequest,
    AudioConfigResponse,
)
from .participant import (
    ParticipantResponse,
    ParticipantUpdateRequest,
    ParticipantListResponse,
    ParticipantInviteRequest,
    ParticipantInviteResponse,
)
from .webhook import (
    WebhookEvent,
    WebhookResponse,
    ACSWebhookEvent,
    MediaWebhookEvent,
)
from .voice_live import (
    VoiceLiveStatusResponse,
    VoiceLiveSessionResponse,
    VoiceLiveConfigRequest,
    VoiceLiveStatusMessage,
    VoiceLiveErrorMessage,
    VoiceLiveTextMessage,
    VoiceLiveMetricsMessage,
    VoiceLiveControlMessage,
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

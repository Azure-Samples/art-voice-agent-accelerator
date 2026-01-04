"""
V1 API Handlers
===============

Business logic handlers for V1 API endpoints.

Handler Architecture:
- VoiceHandler: Unified handler for both ACS and Browser (Phase 3 replacement)
- MediaHandler: Deprecated alias → VoiceHandler (for backward compatibility)
- acs_call_lifecycle: ACS call lifecycle management
- dtmf_validation_lifecycle: DTMF validation handling

Voice channel handlers live in:
    apps/artagent/backend/voice/
"""

# Voice channel imports - all from unified voice module
from apps.artagent.backend.voice import (
    ACSMessageKind,
    BROWSER_PCM_SAMPLE_RATE,
    BROWSER_SILENCE_GAP_SECONDS,
    BROWSER_SPEECH_RMS_THRESHOLD,
    BargeInController,
    RMS_SILENCE_THRESHOLD,
    RouteTurnThread,
    SILENCE_GAP_MS,
    SpeechCascadeHandler,
    SpeechEvent,
    SpeechEventType,
    SpeechSDKThread,
    ThreadBridge,
    TransportType,
    VOICE_LIVE_PCM_SAMPLE_RATE,
    VOICE_LIVE_SILENCE_GAP_SECONDS,
    VOICE_LIVE_SPEECH_RMS_THRESHOLD,
    VoiceHandler,
    VoiceHandlerConfig,
    VoiceLiveSDKHandler,
    pcm16le_rms,
)

# DEPRECATED: MediaHandler is now an alias to VoiceHandler
# All new code should use VoiceHandler directly
MediaHandler = VoiceHandler
MediaHandlerConfig = VoiceHandlerConfig
ACSMediaHandler = VoiceHandler  # Legacy alias


__all__ = [
    # Speech processing (generic)
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "RouteTurnThread",
    "SpeechSDKThread",
    "BargeInController",
    # Unified voice handler (new - Phase 3)
    "VoiceHandler",
    "VoiceHandlerConfig",
    "TransportType",
    "ACSMessageKind",
    # Legacy (deprecated - Phase 2)
    "MediaHandler",
    "MediaHandlerConfig",
    "ACSMediaHandler",
    # VoiceLive
    "VoiceLiveSDKHandler",
    # Audio utilities
    "pcm16le_rms",
    "RMS_SILENCE_THRESHOLD",
    "SILENCE_GAP_MS",
    "BROWSER_PCM_SAMPLE_RATE",
    "BROWSER_SPEECH_RMS_THRESHOLD",
    "BROWSER_SILENCE_GAP_SECONDS",
    "VOICE_LIVE_PCM_SAMPLE_RATE",
    "VOICE_LIVE_SPEECH_RMS_THRESHOLD",
    "VOICE_LIVE_SILENCE_GAP_SECONDS",
]

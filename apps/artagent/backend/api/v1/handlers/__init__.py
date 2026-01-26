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

# MediaHandler has been removed - use VoiceHandler instead
# Migration completed 2026-01-05


__all__ = [
    # Speech processing (generic)
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "RouteTurnThread",
    "SpeechSDKThread",
    "BargeInController",
    # Unified voice handler
    "VoiceHandler",
    "VoiceHandlerConfig",
    "TransportType",
    "ACSMessageKind",
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

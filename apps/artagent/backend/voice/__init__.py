"""
Voice Channels - Speech Orchestration Layer
============================================

Protocol-agnostic voice processing handlers that sit between transport layers
(ACS, Websocket, VoiceLive) and AI orchestrators.

Architecture:
    Transport Layer (ACS/Websocket/VoiceLive SDK)
           │
           ▼
    Voice Channels (this module)
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
  Speech      VoiceLive
  Cascade     SDK Handler
  Handler
    │             │
    ▼             ▼
  Cascade     Live
  Adapter     Orchestrator


Structure:
    voice/
    ├── speech_cascade/
    │   ├── handler.py      # SpeechCascadeHandler (three-thread architecture)
    │   ├── orchestrator.py # CascadeOrchestratorAdapter (unified agents)
    │   └── metrics.py      # STT/turn/barge-in metrics
    ├── voicelive/
    │   ├── handler.py      # VoiceLiveSDKHandler
    │   ├── orchestrator.py # LiveOrchestrator (VoiceLive SDK, uses UnifiedAgent)
    │   └── metrics.py      # OTel latency metrics
    ├── shared/
    │   ├── base.py             # OrchestratorContext/Result data classes
    │   └── config_resolver.py  # Scenario-aware config resolution
    └── handoffs/
        └── context.py      # HandoffContext/HandoffResult dataclasses

Note: The handoff_map (tool_name → agent_name) is built dynamically from agent
YAML declarations via `build_handoff_map()` in agents/loader.py. See
docs/architecture/handoff-inventory.md for the full handoff architecture.
"""

# =============================================================================
# LIGHTWEIGHT IMPORTS (always available)
# =============================================================================

# Handoff context dataclasses (strategies removed - see handoff-inventory.md)
from .handoffs import (
    HandoffContext,
    HandoffResult,
)

# Shared orchestrator data classes and config resolution (lightweight)
from .shared import (
    DEFAULT_START_AGENT,
    OrchestratorContext,
    OrchestratorResult,
    TransportType,
    resolve_from_app_state,
    resolve_orchestrator_config,
)

# Cascade orchestrator (lightweight - no ACS/Speech SDK dependencies)
from .speech_cascade.orchestrator import (
    CascadeConfig,
    CascadeOrchestratorAdapter,
    create_cascade_orchestrator_func,
    get_cascade_orchestrator,
)

# Metrics (lightweight)
from .speech_cascade.metrics import (
    record_barge_in,
    record_stt_recognition,
    record_turn_processing,
)

# =============================================================================
# LAZY IMPORTS (heavy components - loaded on demand)
# =============================================================================

# Components that require heavy dependencies (Speech SDK, ACS, etc.)
# are lazy-loaded to enable use of orchestrator in evaluation notebooks
# without requiring full runtime environment.

_SPEECH_CASCADE_HANDLER_EXPORTS = {
    "BargeInController",
    "ResponseSender",
    "RouteTurnThread",
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "SpeechSDKThread",
    "ThreadBridge",
    "TranscriptEmitter",
}

_TTS_EXPORTS = {
    "TTSPlayback",
    "SAMPLE_RATE_ACS",
    "SAMPLE_RATE_BROWSER",
}

_VOICELIVE_EXPORTS = {
    "CALL_CENTER_TRIGGER_PHRASES",
    "TRANSFER_TOOL_NAMES",
    "LiveOrchestrator",
    "VoiceLiveSDKHandler",
    "record_llm_ttft",
    "record_stt_latency",
    "record_tts_ttfb",
    "record_turn_complete",
    "register_voicelive_orchestrator",
    "unregister_voicelive_orchestrator",
}

# VoiceHandler (Phase 3 unified handler) - lazy loaded
_VOICEHANDLER_EXPORTS = {
    "VoiceHandler",
    "VoiceHandlerConfig",
    "pcm16le_rms",
    "ACSMessageKind",
    "RMS_SILENCE_THRESHOLD",
    "SILENCE_GAP_MS",
    "VOICE_LIVE_PCM_SAMPLE_RATE",
    "VOICE_LIVE_SPEECH_RMS_THRESHOLD",
    "VOICE_LIVE_SILENCE_GAP_SECONDS",
    "BROWSER_PCM_SAMPLE_RATE",
    "BROWSER_SPEECH_RMS_THRESHOLD",
    "BROWSER_SILENCE_GAP_SECONDS",
}

_MESSAGING_EXPORTS = {
    "BrowserBargeInController",
    "broadcast_session_envelope",
    "make_assistant_envelope",
    "make_assistant_streaming_envelope",
    "make_envelope",
    "make_event_envelope",
    "make_status_envelope",
    "send_response_to_acs",
    "send_session_envelope",
    "send_tts_audio",
    "send_user_partial_transcript",
    "send_user_transcript",
}


def __getattr__(name: str):
    """Lazy import for heavy components to avoid import-time dependencies."""
    if name in _SPEECH_CASCADE_HANDLER_EXPORTS:
        from .speech_cascade import handler
        return getattr(handler, name)
    if name in _TTS_EXPORTS:
        from . import tts  # TTSPlayback moved from speech_cascade.tts to voice.tts
        return getattr(tts, name)
    if name in _VOICELIVE_EXPORTS:
        from . import voicelive
        return getattr(voicelive, name)
    if name in _VOICEHANDLER_EXPORTS:
        from . import handler as voice_handler_module
        return getattr(voice_handler_module, name)
    if name in _MESSAGING_EXPORTS:
        from . import messaging
        return getattr(messaging, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Speech Cascade Handler (STT→LLM→TTS) - lazy loaded
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "RouteTurnThread",
    "SpeechSDKThread",
    "BargeInController",
    "ResponseSender",
    "TranscriptEmitter",
    # Speech Cascade Metrics - direct import
    "record_stt_recognition",
    "record_turn_processing",
    "record_barge_in",
    # Unified TTS Playback - lazy loaded
    "TTSPlayback",
    "SAMPLE_RATE_BROWSER",
    "SAMPLE_RATE_ACS",
    # VoiceLive SDK Handler - lazy loaded
    "VoiceLiveSDKHandler",
    # VoiceLive Metrics - lazy loaded
    "record_llm_ttft",
    "record_tts_ttfb",
    "record_stt_latency",
    "record_turn_complete",
    # VoiceHandler (Phase 3 unified) - lazy loaded
    "VoiceHandler",
    "VoiceHandlerConfig",
    "pcm16le_rms",
    "ACSMessageKind",
    "RMS_SILENCE_THRESHOLD",
    "SILENCE_GAP_MS",
    "VOICE_LIVE_PCM_SAMPLE_RATE",
    "VOICE_LIVE_SPEECH_RMS_THRESHOLD",
    "VOICE_LIVE_SILENCE_GAP_SECONDS",
    "BROWSER_PCM_SAMPLE_RATE",
    "BROWSER_SPEECH_RMS_THRESHOLD",
    "BROWSER_SILENCE_GAP_SECONDS",
    # Orchestrator Data Classes - direct import
    "OrchestratorContext",
    "OrchestratorResult",
    "TransportType",
    # Cascade Orchestrator (unified agents) - direct import
    "CascadeOrchestratorAdapter",
    "CascadeConfig",
    "get_cascade_orchestrator",
    "create_cascade_orchestrator_func",
    # VoiceLive Orchestrator - lazy loaded
    "LiveOrchestrator",
    "TRANSFER_TOOL_NAMES",
    "CALL_CENTER_TRIGGER_PHRASES",
    # Config Resolution - direct import
    "DEFAULT_START_AGENT",
    "resolve_orchestrator_config",
    "resolve_from_app_state",
    # Handoff Context - direct import
    "HandoffContext",
    "HandoffResult",
    # Messaging (WebSocket helpers) - lazy loaded
    "send_tts_audio",
    "send_response_to_acs",
    "send_user_transcript",
    "send_user_partial_transcript",
    "send_session_envelope",
    "broadcast_session_envelope",
    "make_envelope",
    "make_status_envelope",
    "make_assistant_envelope",
    "make_assistant_streaming_envelope",
    "make_event_envelope",
    "BrowserBargeInController",
]

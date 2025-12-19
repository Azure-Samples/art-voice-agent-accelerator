"""
Voice Channels - Speech Orchestration Layer
============================================

Protocol-agnostic voice processing handlers that sit between transport layers
(ACS, WebRTC, VoiceLive) and AI orchestrators.

Architecture:
    Transport Layer (ACS/WebRTC/VoiceLive SDK)
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

# Speech Cascade (STT→LLM→TTS three-thread architecture)
# Handoff context dataclasses (strategies removed - see handoff-inventory.md)
from .handoffs import (
    HandoffContext,
    HandoffResult,
)

# Messaging (WebSocket helpers for voice transports)
from .messaging import (
    BrowserBargeInController,
    broadcast_session_envelope,
    make_assistant_envelope,
    make_assistant_streaming_envelope,
    make_envelope,
    make_event_envelope,
    make_status_envelope,
    send_response_to_acs,
    send_session_envelope,
    send_tts_audio,
    send_user_partial_transcript,
    send_user_transcript,
)

# Shared orchestrator data classes and config resolution
from .shared import (
    DEFAULT_START_AGENT,
    OrchestratorContext,
    OrchestratorResult,
    resolve_from_app_state,
    resolve_orchestrator_config,
)
from .speech_cascade import (  # Orchestrator (co-located with handler); Unified TTS Playback
    SAMPLE_RATE_ACS,
    SAMPLE_RATE_BROWSER,
    BargeInController,
    CascadeOrchestratorAdapter,
    ResponseSender,
    RouteTurnThread,
    SpeechCascadeHandler,
    SpeechEvent,
    SpeechEventType,
    SpeechSDKThread,
    ThreadBridge,
    TranscriptEmitter,
    TTSPlayback,
    record_barge_in,
    record_stt_recognition,
    record_turn_processing,
)

# Cascade orchestrator factory functions (re-exported from speech_cascade)
from .speech_cascade.orchestrator import (
    CascadeConfig,
    create_cascade_orchestrator_func,
    get_cascade_orchestrator,
)

# VoiceLive SDK (Azure VoiceLive + multi-agent)
from .voicelive import (  # Orchestrator (co-located with handler)
    CALL_CENTER_TRIGGER_PHRASES,
    TRANSFER_TOOL_NAMES,
    LiveOrchestrator,
    VoiceLiveSDKHandler,
    record_llm_ttft,
    record_stt_latency,
    record_tts_ttfb,
    record_turn_complete,
)

__all__ = [
    # Speech Cascade Handler (STT→LLM→TTS)
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "RouteTurnThread",
    "SpeechSDKThread",
    "BargeInController",
    "ResponseSender",
    "TranscriptEmitter",
    # Speech Cascade Metrics
    "record_stt_recognition",
    "record_turn_processing",
    "record_barge_in",
    # Unified TTS Playback
    "TTSPlayback",
    "SAMPLE_RATE_BROWSER",
    "SAMPLE_RATE_ACS",
    # VoiceLive SDK Handler
    "VoiceLiveSDKHandler",
    # VoiceLive Metrics
    "record_llm_ttft",
    "record_tts_ttfb",
    "record_stt_latency",
    "record_turn_complete",
    # Orchestrator Data Classes
    "OrchestratorContext",
    "OrchestratorResult",
    # Cascade Orchestrator (unified agents)
    "CascadeOrchestratorAdapter",
    "CascadeConfig",
    "get_cascade_orchestrator",
    "create_cascade_orchestrator_func",
    # VoiceLive Orchestrator
    "LiveOrchestrator",
    "TRANSFER_TOOL_NAMES",
    "CALL_CENTER_TRIGGER_PHRASES",
    # Config Resolution
    "DEFAULT_START_AGENT",
    "resolve_orchestrator_config",
    "resolve_from_app_state",
    # Handoff Context
    "HandoffContext",
    "HandoffResult",
    # Messaging (WebSocket helpers)
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

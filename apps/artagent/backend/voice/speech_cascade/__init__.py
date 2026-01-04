"""
Speech Cascade - Three-Thread STT→LLM→TTS Architecture
=======================================================

Protocol-agnostic speech processing implementing the three-thread architecture
for low-latency voice interactions.

Threads:
    🧵 Thread 1: Speech SDK Thread (Never Blocks)
        - Continuous audio recognition
        - Immediate barge-in detection via on_partial callbacks

    🧵 Thread 2: Route Turn Thread (Blocks on Queue Only)
        - AI processing and response generation
        - Orchestrator delegation for TTS and playback

    🧵 Thread 3: Main Event Loop (Never Blocks)
        - Task cancellation for barge-in scenarios
        - Non-blocking coordination with transport layer

Usage:
    from apps.artagent.backend.voice.speech_cascade import (
        SpeechCascadeHandler,
        SpeechEvent,
        SpeechEventType,
        record_stt_recognition,
    )

Note:
    TTSPlayback is now in apps.artagent.backend.voice.tts (not speech_cascade)
"""

# Orchestrator is lightweight - direct import for evaluation use cases
from .orchestrator import CascadeOrchestratorAdapter, StateKeys

# Metrics are lightweight - direct import
from .metrics import (
    record_barge_in,
    record_stt_recognition,
    record_turn_processing,
)

# Heavy handler components are lazy-loaded to avoid Speech SDK dependencies
# when only using orchestrator (e.g., in Jupyter notebooks for evaluation)
_HANDLER_EXPORTS = {
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


def __getattr__(name: str):
    """Lazy import for handler components."""
    if name in _HANDLER_EXPORTS:
        from . import handler
        return getattr(handler, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Handler components (lazy-loaded)
    "SpeechCascadeHandler",
    "SpeechEvent",
    "SpeechEventType",
    "ThreadBridge",
    "RouteTurnThread",
    "SpeechSDKThread",
    "BargeInController",
    "ResponseSender",
    "TranscriptEmitter",
    # Orchestrator shim (direct import)
    "CascadeOrchestratorAdapter",
    "StateKeys",  # Re-export of SessionStateKeys for backward compatibility
    # Metrics (direct import)
    "record_stt_recognition",
    "record_turn_processing",
    "record_barge_in",
]

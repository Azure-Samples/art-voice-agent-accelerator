"""
Voice Messaging - WebSocket Communication Layer
================================================

Re-exports WebSocket helpers for voice channel communication.
This module provides a unified interface for messaging across
different voice transports (ACS, Browser, VoiceLive).

Usage:
    from apps.artagent.backend.voice.messaging import (
        send_tts_audio,
        send_response_to_acs,
        send_user_transcript,
        send_user_partial_transcript,
        send_session_envelope,
        broadcast_session_envelope,
        make_envelope,
        make_status_envelope,
        make_assistant_streaming_envelope,
        BrowserBargeInController,
    )

Migration Note:
    These are re-exported from apps.artagent.backend.src.ws_helpers
    for now. The goal is to provide a stable import path while
    the underlying implementation may be refactored.
"""

# ─────────────────────────────────────────────────────────────────────────────
# TTS and Audio Playback
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Browser Barge-In Controller
# Distinct from speech_cascade.BargeInController - this one manages
# browser-specific metadata and UI control messages.
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.src.ws_helpers.barge_in import (
    BargeInController as BrowserBargeInController,
)

# ─────────────────────────────────────────────────────────────────────────────
# Envelope Builders
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.src.ws_helpers.envelopes import (
    make_assistant_envelope,
    make_assistant_streaming_envelope,
    make_envelope,
    make_event_envelope,
    make_status_envelope,
)

# ─────────────────────────────────────────────────────────────────────────────
# Transcript Broadcasting
# ─────────────────────────────────────────────────────────────────────────────
from apps.artagent.backend.src.ws_helpers.shared_ws import (
    broadcast_session_envelope,
    send_response_to_acs,
    send_session_envelope,
    send_tts_audio,
    send_user_partial_transcript,
    send_user_transcript,
)

__all__ = [
    # TTS Playback
    "send_tts_audio",
    "send_response_to_acs",
    # Transcript Broadcasting
    "send_user_transcript",
    "send_user_partial_transcript",
    "send_session_envelope",
    "broadcast_session_envelope",
    # Envelope Builders
    "make_envelope",
    "make_status_envelope",
    "make_assistant_envelope",
    "make_assistant_streaming_envelope",
    "make_event_envelope",
    # Browser Barge-In
    "BrowserBargeInController",
]

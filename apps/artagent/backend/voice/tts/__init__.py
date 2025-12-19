"""
TTS Module - Unified Text-to-Speech for Voice Handlers
=======================================================

This module provides a single source of truth for all TTS operations
across the voice architecture (Browser, ACS, VoiceLive transports).

All TTS goes through TTSPlayback:
- Greetings
- Agent responses
- Announcements
- Status messages

Usage:
    from apps.artagent.backend.voice.tts import TTSPlayback

    # Create with VoiceSessionContext
    tts = TTSPlayback(context, app_state)
    
    # Speak (routes to appropriate transport)
    await tts.speak("Hello!")
    
    # Or use specific transport methods
    await tts.play_to_browser("Hello!")
    await tts.play_to_acs("Hello!")
"""

from __future__ import annotations

from .playback import (
    SAMPLE_RATE_ACS,
    SAMPLE_RATE_BROWSER,
    TTSPlayback,
)

__all__ = [
    "TTSPlayback",
    "SAMPLE_RATE_BROWSER",
    "SAMPLE_RATE_ACS",
]

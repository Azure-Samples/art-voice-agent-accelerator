"""
Application Constants
=====================

Constants, defaults, and non-configurable values used throughout the application.
These are hard-coded values that don't come from environment variables.
"""

from typing import List, Set

# ==============================================================================
# API ENDPOINTS AND PATHS
# ==============================================================================

# V1 API Endpoints
ACS_CALL_OUTBOUND_PATH: str = "/api/v1/calls/initiate"
ACS_CALL_INBOUND_PATH: str = "/api/v1/calls/answer"
ACS_CALL_CALLBACK_PATH: str = "/api/v1/calls/callbacks"

# V1 WebSocket Endpoints
ACS_WEBSOCKET_PATH: str = "/api/v1/media/stream"

# ==============================================================================
# AUDIO PROCESSING CONSTANTS
# ==============================================================================

# Audio configuration for speech processing
RATE: int = 16000  # Sample rate for audio processing
CHANNELS: int = 1  # Mono audio
FORMAT: int = 16  # PCM16 format for audio
CHUNK: int = 1024  # Size of audio chunks to process

# ==============================================================================
# VOICE AND TTS CONSTANTS
# ==============================================================================

# Available voice options (for reference/documentation)
AVAILABLE_VOICES = {
    "standard": [
        "en-US-AvaMultilingualNeural",  # Female
        "en-US-AndrewMultilingualNeural",  # Male
        "en-US-EmmaMultilingualNeural",  # Female
        "en-US-BrianMultilingualNeural",  # Male
    ],
    "turbo": [
        "en-US-AlloyTurboMultilingualNeural",  # Male
        "en-US-EchoTurboMultilingualNeural",  # Male
        "en-US-FableTurboMultilingualNeural",  # Neutral
        "en-US-OnyxTurboMultilingualNeural",  # Male
        "en-US-NovaTurboMultilingualNeural",  # Female
        "en-US-ShimmerTurboMultilingualNeural",  # Female
    ],
    "hd": [
        # Premium Neural HD Voices (Central India, East Asia, East US, Southeast Asia, West US only)
        "en-US-Adam:DragonHDLatestNeural",  # Male
        "en-US-Andrew:DragonHDLatestNeural",  # Male
        "en-US-Ava:DragonHDLatestNeural",  # Female
        "en-US-Brian:DragonHDLatestNeural",  # Male
        "en-US-Emma:DragonHDLatestNeural",  # Female
    ],
}

# TTS streaming markers
TTS_END: Set[str] = {";", ".", "?", "!"}

# Stop words for conversation termination
STOP_WORDS: List[str] = ["goodbye", "exit", "see you later", "bye"]

# ==============================================================================
# DEFAULT MESSAGES
# ==============================================================================

# Default greeting message
GREETING: str = """Hi there from XYZ Insurance! What can I help you with today?"""

# ==============================================================================
# FEATURE FLAGS (Default Values)
# ==============================================================================

# These can be overridden by environment variables in app_settings.py
DEFAULT_VAD_SEMANTIC_SEGMENTATION: bool = False
DEFAULT_SILENCE_DURATION_MS: int = 1300
DEFAULT_DTMF_VALIDATION_ENABLED: bool = False
DEFAULT_ENABLE_AUTH_VALIDATION: bool = False

# ==============================================================================
# SUPPORTED LANGUAGES
# ==============================================================================

SUPPORTED_LANGUAGES: List[str] = [
    "en-US",
    "es-ES",
    "fr-FR",
    "ko-KR",
    "it-IT",
]

# ==============================================================================
# DEFAULT AUDIO FORMAT
# ==============================================================================

DEFAULT_AUDIO_FORMAT: str = "pcm"

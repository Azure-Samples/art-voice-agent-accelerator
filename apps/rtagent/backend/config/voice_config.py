"""
Voice and TTS Configuration
============================

All voice-related settings including TTS voices, speech processing,
and audio configuration for the real-time voice agent.
"""

import os
import yaml
from typing import Dict, Any

# ==============================================================================
# VOICE CONFIGURATION CACHE
# ==============================================================================

_voice_cache: Dict[str, str] = {}


def get_agent_voice(agent_config_path: str) -> str:
    """Extract voice from agent YAML configuration. Cached to avoid repeated file reads."""
    if agent_config_path in _voice_cache:
        return _voice_cache[agent_config_path]

    try:
        with open(agent_config_path, "r", encoding="utf-8") as file:
            agent_config = yaml.safe_load(file)
            voice_config = agent_config.get("voice", {})
            if isinstance(voice_config, dict):
                voice_name = voice_config.get("voice_name") or voice_config.get("name")
                if voice_name:
                    _voice_cache[agent_config_path] = voice_name
                    return voice_name
            elif isinstance(voice_config, str):
                _voice_cache[agent_config_path] = voice_config
                return voice_config

        # Default voice if no valid configuration found
        _voice_cache[agent_config_path] = "en-US-AvaMultilingualNeural"
        return "en-US-AvaMultilingualNeural"

    except Exception:
        _voice_cache[agent_config_path] = "en-US-AvaMultilingualNeural"
        return "en-US-AvaMultilingualNeural"


# ==============================================================================
# VOICE AND TTS SETTINGS
# ==============================================================================

# Agent configuration paths for voice extraction
AGENT_AUTH_CONFIG = os.getenv(
    "AGENT_AUTH_CONFIG", "apps/rtagent/backend/src/agents/artagent/agent_store/auth_agent.yaml"
)

# Primary TTS voice configuration
GREETING_VOICE_TTS = os.getenv("GREETING_VOICE_TTS") or get_agent_voice(
    AGENT_AUTH_CONFIG
)

# TTS behavior settings
DEFAULT_VOICE_STYLE = os.getenv("DEFAULT_VOICE_STYLE", "neutral")
DEFAULT_VOICE_RATE = os.getenv("DEFAULT_VOICE_RATE", "0%")

# TTS audio format settings
TTS_SAMPLE_RATE_UI = int(os.getenv("TTS_SAMPLE_RATE_UI", "48000"))
TTS_SAMPLE_RATE_ACS = int(os.getenv("TTS_SAMPLE_RATE_ACS", "16000"))
TTS_CHUNK_SIZE = int(os.getenv("TTS_CHUNK_SIZE", "1024"))
TTS_PROCESSING_TIMEOUT = float(os.getenv("TTS_PROCESSING_TIMEOUT", "8.0"))

# ==============================================================================
# SPEECH RECOGNITION SETTINGS
# ==============================================================================

# VAD (Voice Activity Detection) settings
VAD_SEMANTIC_SEGMENTATION = (
    os.getenv("VAD_SEMANTIC_SEGMENTATION", "false").lower() == "true"
)
SILENCE_DURATION_MS = int(os.getenv("SILENCE_DURATION_MS", "1300"))

# Audio format configuration
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "pcm")

# Speech processing timeouts
STT_PROCESSING_TIMEOUT = float(os.getenv("STT_PROCESSING_TIMEOUT", "10.0"))

# Language support
RECOGNIZED_LANGUAGE = os.getenv(
    "RECOGNIZED_LANGUAGE", "en-US,es-ES,fr-FR,ko-KR,it-IT,pt-PT,pt-BR"
).split(",")

# ==============================================================================
# AZURE VOICE LIVE SETTINGS
# ==============================================================================

AZURE_VOICE_LIVE_ENDPOINT = os.getenv("AZURE_VOICE_LIVE_ENDPOINT", "")
AZURE_VOICE_API_KEY = os.getenv("AZURE_VOICE_API_KEY", "")
AZURE_VOICE_LIVE_MODEL = os.getenv("AZURE_VOICE_LIVE_MODEL", "gpt-4o")

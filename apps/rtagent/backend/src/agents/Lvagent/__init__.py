"""
Azure Live Voice Agent Module.

This module implements a real-time voice agent using Azure Voice Live API
with Azure AI Agent Service, following the copilot instructions for 
low-latency voice applications.

Key features:
- Token-based authentication with API key fallback
- Real-time audio streaming with VAD
- Proper session management and error handling
- OpenTelemetry instrumentation ready
"""

from .base import (
    AzureLiveVoiceAgent,
    LvaModel,
    LvaAgentBinding,
    LvaSessionCfg,
    DEFAULT_API_VERSION,
    DEFAULT_SAMPLE_RATE_HZ,
    DEFAULT_CHUNK_MS,
)

from .factory import build_lva_from_yaml

from .transport import WebSocketTransport

from .audio_io import (
    MicSource,
    SpeakerSink,
    pcm_to_base64,
)

__all__ = [
    # Main classes
    "AzureLiveVoiceAgent",
    "LvaModel", 
    "LvaAgentBinding",
    "LvaSessionCfg",
    
    # Factory functions
    "build_lva_from_yaml",
    
    # Transport
    "WebSocketTransport",
    
    # Audio I/O
    "MicSource",
    "SpeakerSink", 
    "pcm_to_base64",
    
    # Constants
    "DEFAULT_API_VERSION",
    "DEFAULT_SAMPLE_RATE_HZ", 
    "DEFAULT_CHUNK_MS",
]
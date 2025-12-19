"""Real-Time Voice Agent with Azure Cognitive Services.

This package provides comprehensive text-to-speech and speech recognition capabilities
using Azure Cognitive Services, optimized for real-time voice applications.
"""

__version__ = "1.0.0"
__author__ = "Pablo Salvador"
__email__ = "pablosalvador10@gmail.com"

# Import main classes for convenience
try:
    from .speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
    from .speech.text_to_speech import SpeechSynthesizer

    __all__ = [
        "SpeechSynthesizer",
        "StreamingSpeechRecognizerFromBytes",
    ]
except ImportError:
    # Handle import errors gracefully during documentation build
    __all__ = []

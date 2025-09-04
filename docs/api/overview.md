# API Overview

The Real-Time Voice Agent provides a comprehensive set of APIs for building voice-enabled applications with Azure Cognitive Services.

## Core Components

### Speech Synthesis
- **[SpeechSynthesizer](speech-synthesis.md)** - Text-to-speech engine with neural voices
- Multiple output formats: audio files, streaming frames, speaker playback
- Advanced voice control with SSML, styles, and prosody
- Intelligent environment detection for headless deployments

### Speech Recognition  
- **[StreamingSpeechRecognizer](speech-recognition.md)** - Real-time speech-to-text
- Continuous recognition with minimal latency
- Language detection and speaker diarization
- Neural audio processing for improved accuracy

### Utilities
- **[Text Processing](utilities.md)** - Sentence splitting and language optimization
- **[SSML Generation](utilities.md)** - Advanced markup for voice control
- **[Authentication](utilities.md)** - Azure credential management

## Authentication

All components support flexible authentication:

```python
# API Key (development/testing)
synthesizer = SpeechSynthesizer(
    key="your-speech-key",
    region="eastus"
)

# Managed Identity (production)
synthesizer = SpeechSynthesizer(
    region="eastus"  # Uses DefaultAzureCredential
)
```

## Environment Variables

Configure services using environment variables:

```bash
# Required for API key authentication
AZURE_SPEECH_KEY=your-subscription-key
AZURE_SPEECH_REGION=eastus

# Required for managed identity
AZURE_SPEECH_RESOURCE_ID=/subscriptions/.../resourceGroups/.../providers/Microsoft.CognitiveServices/accounts/...

# Optional configuration
AZURE_SPEECH_ENDPOINT=https://custom-endpoint.cognitiveservices.azure.com
TTS_ENABLE_LOCAL_PLAYBACK=true
```

## Observability

Built-in OpenTelemetry support for production monitoring:

```python
# Enable distributed tracing
synthesizer = SpeechSynthesizer(
    region="eastus",
    enable_tracing=True,
    call_connection_id="session-12345"
)

# All operations automatically traced
audio = synthesizer.synthesize_speech("Hello world")
```

## Error Handling

Robust error handling with graceful degradation:

- Authentication failures with clear error messages
- Network timeouts with automatic retry logic
- Audio hardware unavailable (headless environments)
- Service quota limits and rate limiting

## Performance Considerations

- **Concurrent synthesis limiting** - Built-in semaphore prevents service overload
- **Credential caching** - Automatic token refresh and credential reuse  
- **Lazy initialization** - Audio components created only when needed
- **Memory efficiency** - Streaming operations minimize memory usage

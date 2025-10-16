# Speech Synthesis API

The Real-Time Voice Agent provides enterprise-grade text-to-speech capabilities through the `SpeechSynthesizer` class, built on Azure Speech Services with comprehensive integration features.

## Key Features

- **Multiple authentication methods**: API Key and Azure Entra ID (Default Credentials)
- **Real-time synthesis**: Base64 frame streaming for WebSocket clients
- **Local speaker playback**: Intelligent headless environment detection
- **OpenTelemetry tracing**: Integration for Application Insights monitoring
- **Concurrent synthesis limiting**: Prevents service overload
- **Advanced voice control**: Neural styles, prosody, multilingual support

## SpeechSynthesizer Class

Located in `src/speech/text_to_speech.py`, the `SpeechSynthesizer` provides comprehensive text-to-speech functionality with Azure integration.

### Authentication Methods

#### Azure Entra ID (Recommended for Production)
```python
from src.speech.text_to_speech import SpeechSynthesizer

# Uses DefaultAzureCredential - no API key required
synthesizer = SpeechSynthesizer(
    region="eastus",
    voice="en-US-JennyMultilingualNeural",
    enable_tracing=True
)
```

#### API Key (Development/Testing)
```python
# Traditional API key authentication
synthesizer = SpeechSynthesizer(
    key="your-speech-key",
    region="eastus",
    voice="en-US-AriaNeural"
)
```

### Basic Usage Examples

#### Simple Text-to-Speech
```python
# Synthesize to memory
audio_data = synthesizer.synthesize_speech(
    "Hello! Welcome to our voice application.",
    style="chat",
    rate="+10%"
)

# Save to file
with open("output.wav", "wb") as f:
    f.write(audio_data)
```

#### Real-time Streaming for WebSocket
```python
# Generate base64-encoded frames for streaming
frames = synthesizer.synthesize_to_base64_frames(
    "This is real-time streaming audio",
    sample_rate=16000
)

# Send frames to WebSocket client
for frame in frames:
    websocket.send(frame)
```

#### Local Speaker Playback
```python
# Play audio through system speakers (if available)
synthesizer = SpeechSynthesizer(
    key="your-key",
    region="eastus",
    playback="auto"  # Automatic hardware detection
)

# Speak text directly
synthesizer.start_speaking_text(
    "This will play through your speakers!",
    voice="en-US-AriaNeural",
    style="excited"
)

# Stop playback
import time
time.sleep(3)
synthesizer.stop_speaking()
```

### Advanced Configuration

#### Production Setup with Managed Identity
```python
import os
from src.speech.text_to_speech import SpeechSynthesizer

# Production configuration
synthesizer = SpeechSynthesizer(
    region=os.getenv("AZURE_SPEECH_REGION"),
    voice="en-US-JennyMultilingualNeural", 
    playback="never",  # Headless deployment
    enable_tracing=True,  # OpenTelemetry monitoring
    call_connection_id="session-abc123"  # Correlation tracking
)

# Validate configuration
if synthesizer.validate_configuration():
    print("✅ Speech synthesizer ready for production")
else:
    print("❌ Configuration validation failed")
```

#### Voice Styles and Prosody Control
```python
# Advanced voice styling
audio = synthesizer.synthesize_speech(
    "Production-ready voice synthesis",
    voice="en-US-AriaNeural",
    style="news",  # Available: chat, cheerful, sad, angry, etc.
    rate="+5%",    # Speed adjustment
    pitch="+2Hz",  # Pitch control
    volume="+10dB" # Volume adjustment
)
```

### Environment Configuration

Required environment variables for production deployment:

```bash
# Azure Speech Services
AZURE_SPEECH_REGION=eastus
AZURE_SPEECH_RESOURCE_ID=/subscriptions/.../resourceGroups/.../providers/Microsoft.CognitiveServices/accounts/...

# Optional: Custom endpoint
AZURE_SPEECH_ENDPOINT=https://your-custom-endpoint.cognitiveservices.azure.com

# Optional: Audio playback control
TTS_ENABLE_LOCAL_PLAYBACK=false  # Set to false for headless environments
```

### Error Handling and Validation

#### Configuration Validation
```python
# Test configuration before use
if synthesizer.validate_configuration():
    print('✅ Configuration is valid')
    
    # Test basic synthesis
    audio_data = synthesizer.synthesize_speech("Hello, world!")
    print(f'✅ Generated {len(audio_data)} bytes of audio')
else:
    print('❌ Configuration validation failed')
```

#### Common Issues

**Authentication Errors**
```bash
# Verify Azure credentials
az account show
az cognitiveservices account list
```

**Audio Hardware Issues**
```python
# Check headless environment detection
from src.speech.text_to_speech import _is_headless
print(f"Headless environment: {_is_headless()}")
```

**Import Errors**
```bash
# Ensure dependencies are installed
pip install azure-cognitiveservices-speech
python -c "import src.speech.text_to_speech; print('✅ Import successful')"
```

### OpenTelemetry Integration

The `SpeechSynthesizer` includes built-in tracing for production monitoring:

```python
# Enable comprehensive tracing
synthesizer = SpeechSynthesizer(
    region="eastus",
    enable_tracing=True,
    call_connection_id="acs-call-123"  # Correlation ID
)

# All operations automatically traced with:
# - Session-level spans for complete request lifecycle  
# - Service dependency mapping for Azure Monitor App Map
# - Call correlation across distributed components
```

### Performance Considerations

- **Connection pooling**: Default limit of 4 concurrent synthesis operations
- **Memory efficiency**: Streaming operations with automatic resource cleanup
- **Lazy initialization**: Audio components initialized only when needed
- **Headless detection**: Automatic fallback for containerized environments

### Integration with Container Apps

For Azure Container Apps deployment, ensure proper configuration:

```dockerfile
# Dockerfile example
FROM python:3.11-slim

# Set environment for headless operation
ENV TTS_ENABLE_LOCAL_PLAYBACK=false
ENV AZURE_SPEECH_REGION=eastus

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY src/ ./src/
CMD ["python", "-m", "your_app"]
```

## API Integration

The speech synthesis functionality integrates with the main API endpoints - see **[API Reference](../api/api-reference.md)** for complete endpoint documentation:

- **Call Management** - TTS for outbound call prompts and conversation responses
- **Media Streaming** - Real-time TTS synthesis for ACS call conversations  
- **Health Monitoring** - TTS service validation and voice testing

For complete API documentation, see the [API Overview](../api/README.md).
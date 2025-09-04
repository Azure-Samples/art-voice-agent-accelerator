# Quick Start Guide

Get up and running with the Real-Time Voice Agent in just a few minutes.

## Prerequisites

- Python 3.11+
- Azure Subscription with Cognitive Services
- Azure Speech Services resource

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/pablosalvador10/gbb-ai-audio-agent.git
cd gbb-ai-audio-agent
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables:**
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Azure credentials
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=eastus
```

## Basic Text-to-Speech

```python
from src.speech.text_to_speech import SpeechSynthesizer

# Initialize synthesizer
synthesizer = SpeechSynthesizer(
    key="your-speech-key",
    region="eastus",
    voice="en-US-JennyMultilingualNeural"
)

# Synthesize speech to memory
audio_data = synthesizer.synthesize_speech(
    "Hello! Welcome to our voice application.",
    style="chat",
    rate="+10%"
)

# Save to file
with open("output.wav", "wb") as f:
    f.write(audio_data)

print(f"Generated {len(audio_data)} bytes of audio")
```

## Real-time Streaming

```python
# Generate base64-encoded frames for streaming
frames = synthesizer.synthesize_to_base64_frames(
    "This is real-time streaming audio",
    sample_rate=16000
)

print(f"Generated {len(frames)} audio frames")
for i, frame in enumerate(frames[:3]):  # Show first 3 frames
    print(f"Frame {i}: {frame[:50]}...")
```

## Local Speaker Playback

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

# Stop if needed
import time
time.sleep(3)
synthesizer.stop_speaking()
```

## Production Configuration

```python
import os
from src.speech.text_to_speech import SpeechSynthesizer

# Production setup with managed identity
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
    
    # Synthesize with advanced options
    audio = synthesizer.synthesize_speech(
        "Production-ready voice synthesis",
        voice="en-US-AriaNeural",
        style="news",
        rate="+5%"
    )
else:
    print("❌ Configuration validation failed")
```

## Next Steps

- **[Configuration Guide](configuration.md)** - Detailed setup options
- **[API Reference](../api/overview.md)** - Complete API documentation  
- **[Architecture](../architecture/overview.md)** - System design and components
- **[Examples](../examples/basic-usage.md)** - More usage examples

## Common Issues

### Authentication Errors
```bash
# Verify your credentials
az account show
az cognitiveservices account list
```

### Audio Hardware Issues
```python
# Check headless environment detection
from src.speech.text_to_speech import _is_headless
print(f"Headless environment: {_is_headless()}")
```

### Import Errors
```bash
# Ensure all dependencies installed
pip install -r requirements.txt

# Check Python path
python -c "import src.speech.text_to_speech; print('✅ Import successful')"
```

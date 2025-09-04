# Speech Synthesis API

The `SpeechSynthesizer` class provides comprehensive text-to-speech capabilities using Azure Cognitive Services. This page documents all public methods and their usage.

## SpeechSynthesizer Class

::: src.speech.text_to_speech.SpeechSynthesizer
    options:
      show_source: true
      show_signature_annotations: true
      separate_signature: true
      merge_init_into_class: true
      docstring_section_style: table
      members_order: source
      group_by_category: true
      show_category_heading: true
      filters:
        - "!^_"  # Hide private methods except __init__
        - "^__init__$"  # But show __init__

## Utility Functions

### Text Processing

::: src.speech.text_to_speech.split_sentences
    options:
      show_source: true
      show_signature_annotations: true

::: src.speech.text_to_speech.auto_style
    options:
      show_source: true
      show_signature_annotations: true

### SSML Generation

::: src.speech.text_to_speech.ssml_voice_wrap
    options:
      show_source: true
      show_signature_annotations: true

## Examples

### Basic Usage

```python
from src.speech.text_to_speech import SpeechSynthesizer

# Initialize with API key
synthesizer = SpeechSynthesizer(
    key="your-speech-key",
    region="eastus",
    voice="en-US-JennyMultilingualNeural"
)

# Synthesize to memory
audio_data = synthesizer.synthesize_speech(
    "Hello, welcome to our voice application!",
    style="chat",
    rate="+10%"
)
```

### Advanced Configuration

```python
# Production configuration with managed identity
synthesizer = SpeechSynthesizer(
    region="eastus",  # Uses managed identity when key=None
    language="en-US",
    voice="en-US-AriaNeural",
    playback="never",  # Headless deployment
    enable_tracing=True,
    call_connection_id="session-abc123"
)

# Generate streaming frames for real-time applications
frames = synthesizer.synthesize_to_base64_frames(
    "This is real-time audio streaming",
    sample_rate=16000,
    style="chat"
)
```

### Speaker Playback

```python
# Local audio playback (development/testing)
synthesizer = SpeechSynthesizer(
    key="your-key",
    region="eastus", 
    playback="auto"  # Only plays if speakers available
)

# Speak text directly through speakers
synthesizer.start_speaking_text(
    "This will play through your speakers",
    voice="en-US-JennyNeural",
    rate="+15%",
    style="excited"
)

# Stop playback if needed
synthesizer.stop_speaking()
```

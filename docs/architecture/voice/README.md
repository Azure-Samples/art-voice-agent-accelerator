# Voice Processing Architecture

The voice module handles all real-time voice interactions including Speech-to-Text (STT), Language Model orchestration, and Text-to-Speech (TTS) for both web browsers and telephone calls.

## Overview

The voice system supports two transport types:
- **Browser**: WebRTC audio at 48kHz for web applications
- **ACS (Azure Communication Services)**: Telephony audio at 16kHz for phone calls

## Directory Structure

```
voice/
├── handler.py                  Main VoiceHandler (recommended)
├── tts/                        Text-to-Speech module
│   └── playback.py             TTS audio playback
├── speech_cascade/             Speech processing pipeline
│   ├── handler.py              3-thread speech handler (STT, Turn, Barge-in)
│   ├── orchestrator.py         LLM routing and turn management
│   ├── tts_processor.py        Text utilities (markdown cleanup, sentence detection)
│   └── metrics.py              Telemetry and metrics
├── shared/                     Shared utilities
│   ├── context.py              Session context for dependency injection
│   └── config_resolver.py     Orchestrator configuration
└── messaging/                  WebSocket helpers
    ├── transcripts.py          Transcript message formatting
    └── barge_in.py             Interrupt handling
```

## Key Components

### VoiceHandler

The main entry point for voice interactions. Manages the complete lifecycle of a voice session.

**Location:** `apps/artagent/backend/voice/handler.py`

```python
from apps.artagent.backend.voice import VoiceHandler, VoiceSessionContext

# Create session context
context = VoiceSessionContext(
    session_id=session_id,
    websocket=ws,
    transport=TransportType.BROWSER,  # or TransportType.ACS
    cancel_event=asyncio.Event(),
    current_agent=agent
)

# Create and start handler
handler = await VoiceHandler.create(config, app_state)
await handler.start()

# Cleanup when done
await handler.stop()
```

### Text-to-Speech (TTS)

Converts text responses into audio and streams them to the user.

**Location:** `apps/artagent/backend/voice/tts/playback.py`

```python
from apps.artagent.backend.voice.tts import TTSPlayback

# Create TTS instance
tts = TTSPlayback(context, app_state)

# Speak to user (automatically routes to browser or ACS)
await tts.speak("Hello! How can I help you?")
```

**Key Features:**
- Automatic transport routing (browser vs telephony)
- Voice customization per agent
- Cancellation support for barge-in
- Streaming for low latency

### Speech Cascade

Processes user speech through a multi-threaded pipeline:

1. **STT Thread**: Converts audio to text using Azure Speech Services
2. **Turn Thread**: Routes conversation turns to appropriate LLM/agent
3. **Barge-in Thread**: Handles user interruptions during agent responses

**Location:** `apps/artagent/backend/voice/speech_cascade/`

The cascade orchestrator manages this flow and coordinates between threads.

### VoiceSessionContext

A shared context object that holds all session state, enabling clean dependency injection.

```python
from apps.artagent.backend.voice.shared import VoiceSessionContext, TransportType

context = VoiceSessionContext(
    session_id="unique-session-id",
    websocket=websocket_connection,
    transport=TransportType.BROWSER,
    cancel_event=asyncio.Event(),
    current_agent=agent_instance
)
```

## Audio Specifications

### Browser Transport (48kHz)
- **Sample Rate**: 48,000 Hz
- **Format**: PCM16 mono
- **Chunk Size**: 9,600 bytes (100ms per chunk)
- **Encoding**: Base64-encoded JSON over WebSocket

### ACS Telephony Transport (16kHz)
- **Sample Rate**: 16,000 Hz
- **Format**: PCM16 mono
- **Chunk Size**: 1,280 bytes (40ms per chunk)
- **Pacing**: 40ms delay between chunks
- **Encoding**: Base64-encoded ACS AudioData messages

## Common Usage Patterns

### Starting a Voice Session

```python
from apps.artagent.backend.voice import VoiceHandler, VoiceSessionContext, TransportType

# 1. Create session context with all needed state
context = VoiceSessionContext(
    session_id=f"session-{uuid.uuid4()}",
    websocket=websocket,
    transport=TransportType.BROWSER,
    cancel_event=asyncio.Event(),
    current_agent=initial_agent
)

# 2. Initialize voice handler
handler = await VoiceHandler.create(agent_config, app_state)
await handler.start()

# Handler automatically manages STT, orchestration, and TTS
```

### Playing Audio to User

```python
from apps.artagent.backend.voice.tts import TTSPlayback

# Create TTS instance
tts = TTSPlayback(context, app_state)

# Simple speak (uses agent's default voice)
await tts.speak("Your account balance is $1,234.56")

# Custom voice override
await tts.speak(
    "Welcome to our bank!",
    voice_name="en-US-JennyNeural",
    style="friendly"
)
```

### Processing Text for TTS

Some LLM responses contain markdown or formatting that needs cleaning:

```python
from apps.artagent.backend.voice.speech_cascade.tts_processor import TTSTextProcessor

# Remove markdown formatting
clean_text = TTSTextProcessor.sanitize_tts_text(
    "**Bold text** and _italic text_"
)
# Result: "Bold text and italic text"

# Split streaming text into complete sentences
sentences, buffer = TTSTextProcessor.process_streaming_text(
    llm_chunk,
    previous_buffer
)
```

## Best Practices

### DO ✅

1. **Use VoiceSessionContext** for passing session state

    ```python
    # Good - clean dependency injection
    context = VoiceSessionContext(session_id=id, websocket=ws, ...)
    tts = TTSPlayback(context, app_state)
    ```

2. **Let TTS auto-route transports**

    ```python
    # Good - automatically handles browser vs ACS
    await tts.speak(text)
    ```

3. **Handle cancellation for barge-in**

    ```python
    # Good - supports user interruptions
    context.cancel_event.set()  # Stops current TTS
    ```

### DON'T ❌

1. **Don't manually manage transports**

    ```python
    # Bad - unnecessary complexity
    if transport == "browser":
        await tts.play_to_browser(text)
    else:
        await tts.play_to_acs(text)
    ```

2. **Don't confuse TTS playback with text processing**

    ```python
    # Bad - tts_processor is not for audio playback
    from voice.speech_cascade.tts_processor import TTSTextProcessor
    # This class only handles text utilities, not audio
    ```

3. **Don't forget to clean up handlers**

    ```python
    # Bad - can cause resource leaks
    handler = await VoiceHandler.create(config, app_state)
    # ... use handler ...
    # Missing: await handler.stop()
    ```

## Telemetry

The voice system emits OpenTelemetry spans for monitoring:

```
tts.synthesize
├── attributes: voice, style, rate, sample_rate, text_length
└── duration: synthesis time

tts.stream.browser | tts.stream.acs
├── attributes: transport, audio_bytes, chunks_sent
└── duration: streaming time

cascade.process_turn
├── invoke_agent {agent_name}
└── tts.synthesize + tts.stream
```

Custom metrics tracked:
- `tts.synthesis.duration_ms` - TTS generation time
- `tts.stream.duration_ms` - Audio streaming time
- `tts.stream.chunks_sent` - Number of audio chunks
- `tts.stream.audio_bytes` - Total audio size

## Troubleshooting

### Audio sounds slow or distorted (ACS only)

**Check**: Verify chunk size is 1,280 bytes (not 640)

```python
# In logs, look for:
# chunk_size=1280 (correct)
# NOT chunk_size=640 (incorrect)
```

**Location**: `apps/artagent/backend/voice/tts/playback.py:490`

### No audio playing

1. Check WebSocket connection is active
2. Verify TTS synthesis succeeded (check logs for "Synthesis complete")
3. Confirm transport type matches endpoint (browser vs ACS)
4. Check for cancellation events interrupting playback

### High latency

Typical TTS latencies:
- Synthesis: 100-500ms (depends on text length)
- First chunk: +50-100ms (encoding + network)
- Total TTFB: 150-600ms

If higher, check:
- Azure region proximity
- Network connectivity
- TTS pool health: `/api/v1/tts/health`

## Testing

### Prerequisites

Install test dependencies first:

```bash
# Using uv (recommended)
uv sync --extra dev

# Or using pip
pip install -e ".[dev]"
```

### Unit Tests

Run the voice handler component tests:

```bash
# Test all voice handler components (context, TTS playback, agent voice resolution)
pytest tests/test_voice_handler_components.py -v

# Test voice handler compatibility layer
pytest tests/test_voice_handler_compat.py -v

# Test cascade orchestrator functionality
pytest tests/test_cascade_orchestrator_entry_points.py -v
pytest tests/test_cascade_llm_processing.py -v

# Run all voice-related tests
pytest tests/ -k "voice or cascade" -v
```

**Optional: Run with coverage reporting** (requires `pytest-cov` from dev dependencies):

```bash
pytest tests/test_voice_handler_components.py --cov=apps.artagent.backend.voice --cov-report=term-missing
```

### Integration Testing

Test the full orchestrator pipeline interactively:

```bash
# Run interactive orchestrator test (browser mode)
./devops/scripts/misc/quick_test.sh

# Or run directly with Python
python devops/scripts/misc/test_orchestrator.py --interactive
```

This will test the complete flow: speech recognition → LLM orchestration → TTS playback.

### Manual Testing

**Browser:**
1. Start the backend server: `uvicorn apps.artagent.backend.main:app --reload`
2. Open web UI at `http://localhost:8000`
3. Start voice conversation
4. Verify clear audio (not slow/choppy)
5. Test barge-in by speaking during response

**ACS Telephony:**
1. Make test call via `/api/v1/call/outbound`
2. Verify natural audio playback
3. Test interruptions (DTMF or speech)
4. Check logs for correct chunk sizes (1,280 bytes for 16kHz)

## Related Documentation

- [Orchestration System](../orchestration/README.md) - How agents are selected and managed
- [Speech Recognition](../speech/recognition.md) - STT implementation details
- [Session Management](../data/README.md) - Session state and lifecycle
- [Telemetry](../telemetry.md) - Monitoring and observability

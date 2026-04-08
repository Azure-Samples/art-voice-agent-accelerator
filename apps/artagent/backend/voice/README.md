# Voice Module - Developer Reference

Quick reference for developers working with the voice processing module.

## Directory Structure

```
voice/
├── README.md                    ← You are here
├── __init__.py                  Public API exports
├── handler.py                   VoiceHandler - main entry point
│
├── tts/                         Text-to-Speech
│   ├── __init__.py
│   └── playback.py              TTSPlayback class
│
├── speech_cascade/              Speech processing pipeline
│   ├── __init__.py
│   ├── handler.py               Multi-threaded speech handler
│   ├── orchestrator.py          Turn routing and LLM coordination
│   ├── tts_processor.py         Text utilities (markdown, sentence detection)
│   └── metrics.py               TTS telemetry
│
├── shared/                      Shared utilities
│   ├── __init__.py
│   ├── context.py               VoiceSessionContext
│   └── config_resolver.py       Agent config resolution
│
└── messaging/                   WebSocket messaging
    ├── __init__.py
    ├── transcripts.py           Transcript formatting
    └── barge_in.py              Barge-in controllers
```

## Quick Start

### Basic Voice Session

```python
from apps.artagent.backend.voice import VoiceHandler, VoiceSessionContext, TransportType
from apps.artagent.backend.voice.tts import TTSPlayback

# 1. Create session context
context = VoiceSessionContext(
    session_id=session_id,
    websocket=ws,
    transport=TransportType.BROWSER,  # or TransportType.ACS
    cancel_event=asyncio.Event(),
    current_agent=agent
)

# 2. Create voice handler
handler = await VoiceHandler.create(config, app_state)
await handler.start()

# 3. Use TTS
tts = TTSPlayback(context, app_state)
await tts.speak("Hello! How can I help you?")

# 4. Cleanup
await handler.stop()
```

## Module Reference

### Core Handlers

| Module | Use For | Status |
|--------|---------|--------|
| `handler.py` (VoiceHandler) | New features and endpoints | ✅ Recommended |
| `api/../media_handler.py` (MediaHandler) | Existing browser/ACS endpoints | ⚠️ Legacy |

### TTS (Text-to-Speech)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `tts/playback.py` | Audio synthesis and streaming | All new code |
| `speech_cascade/tts_processor.py` | Text cleanup utilities | Markdown removal, sentence splitting |

### Speech Processing

| Module | Purpose |
|--------|---------|
| `speech_cascade/handler.py` | STT, Turn processing, Barge-in handling |
| `speech_cascade/orchestrator.py` | Agent selection and LLM routing |
| `speech_cascade/metrics.py` | TTS telemetry recording |

### Infrastructure

| Module | Purpose |
|--------|---------|
| `shared/context.py` | Session state container (VoiceSessionContext) |
| `shared/config_resolver.py` | Resolve orchestrator config from agent |
| `messaging/transcripts.py` | Format WebSocket transcript messages |
| `messaging/barge_in.py` | Handle user interruptions |

## Common Tasks

### Play TTS Audio

```python
from apps.artagent.backend.voice.tts import TTSPlayback

tts = TTSPlayback(context, app_state)

# Auto-routes to browser or ACS based on context.transport
await tts.speak("Your balance is $1,234.56")

# With custom voice
await tts.speak(
    "Welcome!",
    voice_name="en-US-JennyNeural",
    style="friendly"
)
```

### Clean Text for TTS

```python
from apps.artagent.backend.voice.speech_cascade.tts_processor import TTSTextProcessor

# Remove markdown formatting
clean = TTSTextProcessor.sanitize_tts_text("**Bold** and _italic_")

# Split streaming chunks into sentences
sentences, buffer = TTSTextProcessor.process_streaming_text(chunk, buffer)
for sentence in sentences:
    await tts.speak(sentence)
```

### Handle Barge-in (User Interrupts)

```python
# Set cancel event to stop current TTS
context.cancel_event.set()

# Clear for next turn
context.cancel_event.clear()
```

## Audio Format Reference

### Browser (Websocket)
- Sample Rate: **48 kHz**
- Format: PCM16 mono
- Chunk Size: **9,600 bytes** (100ms)
- Transport: WebSocket JSON

### ACS (Telephony)
- Sample Rate: **16 kHz**
- Format: PCM16 mono
- Chunk Size: **1,280 bytes** (40ms)
- Pacing: 40ms between chunks
- Transport: ACS AudioData messages

## File Locations

### Want to modify TTS behavior?
- **Playback logic**: `voice/tts/playback.py`
- **Text processing**: `voice/speech_cascade/tts_processor.py`
- **Azure TTS wrapper**: `src/speech/text_to_speech.py`
- **TTS pool**: `src/pools/tts_pool.py`

### Want to modify speech cascade?
- **Handler threads**: `voice/speech_cascade/handler.py`
- **Turn routing**: `voice/speech_cascade/orchestrator.py`
- **Metrics**: `voice/speech_cascade/metrics.py`

### Want to modify session context?
- **Context definition**: `voice/shared/context.py`
- **Config resolver**: `voice/shared/config_resolver.py`

## Testing

**Prerequisites:** Install dev dependencies first with `uv sync --extra dev` or `pip install -e ".[dev]"`

```bash
# Voice handler component tests
pytest tests/test_voice_handler_components.py -v
pytest tests/test_voice_handler_compat.py -v

# Cascade orchestrator tests
pytest tests/test_cascade_orchestrator_entry_points.py -v
pytest tests/test_cascade_llm_processing.py -v

# Integration tests - full media lifecycle
pytest tests/test_acs_media_lifecycle.py -v

# Run all voice-related tests
pytest tests/ -k "voice or cascade" -v

# Interactive orchestrator test
./devops/scripts/misc/quick_test.sh

# TTS health check
curl http://localhost:8000/api/v1/tts/health
```

## Common Pitfalls

### ❌ Don't use text processor for audio playback
```python
# WRONG - tts_processor is not for playing audio
from voice.speech_cascade.tts_processor import TTSTextProcessor
# This is only for text utilities!
```

### ✅ Use TTSPlayback for audio
```python
# CORRECT
from voice.tts import TTSPlayback
tts = TTSPlayback(context, app_state)
await tts.speak(text)
```

### ❌ Don't manually route transports
```python
# WRONG - unnecessary complexity
if transport == "browser":
    await tts.play_to_browser(text)
else:
    await tts.play_to_acs(text)
```

### ✅ Use transport-agnostic speak()
```python
# CORRECT - auto-routes based on context
await tts.speak(text)
```

## Documentation

For more details see:
- **Architecture Overview**: `docs/architecture/voice/README.md`
- **Troubleshooting**: `docs/operations/troubleshooting.md`
- **Orchestration**: `docs/architecture/orchestration/README.md`

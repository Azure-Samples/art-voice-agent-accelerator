# Handler Architecture

## Overview

This package contains the **transport-level** handlers for ACS media processing.
Voice channel handlers (speech processing, orchestration) have moved to:

```
apps/artagent/backend/voice_channels/
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ENDPOINTS                                │
│  media.py (ACS/phone)     browser.py (web browser)              │
└──────────────┬─────────────────────────┬────────────────────────┘
               │                         │
               ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MediaHandler                               │
│  Unified handler for both transports                            │
│  - Owns TTS/STT pool resources                                  │
│  - Manages WebSocket state                                      │
│  - Routes messages to SpeechCascadeHandler                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              voice_channels/ (NEW LOCATION)                     │
│  - SpeechCascadeHandler: Three-thread STT→LLM→TTS               │
│  - VoiceLiveSDKHandler: Azure VoiceLive + multi-agent           │
│  - voicelive_metrics: Latency tracking                          │
└─────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose | When to modify |
|------|---------|----------------|
| `media_handler.py` | Unified ACS + Browser handler | Adding transport-level features, TTS/STT flow changes |
| `acs_call_lifecycle.py` | ACS call setup/teardown | Phone call initiation, webhooks |
| `dtmf_validation_lifecycle.py` | DTMF validation handling | DTMF flow changes |

### Moved to `voice_channels/`

| File | Purpose |
|------|---------|
| `speech_cascade_handler.py` | Core speech processing (VAD, barge-in, STT pipeline) |
| `voice_live_sdk_handler.py` | VoiceLive SDK integration with multi-agent support |
| `voicelive_metrics.py` | OpenTelemetry metrics for latency tracking |

## Key Concepts

### TransportType

Two transports share the same handler:

```python
class TransportType(Enum):
    ACS = "acs"        # Azure Communication Services (phone calls)
    BROWSER = "browser" # Direct browser WebSocket
```

**ACS**: JSON-wrapped base64 audio, StopAudio commands
**Browser**: Raw PCM bytes, JSON control messages

### Callback Flow

SpeechCascadeHandler emits events via callbacks. MediaHandler implements these:

```python
on_barge_in       → User interrupted, stop TTS
on_greeting       → Play greeting audio  
on_partial        → Show "user is speaking..." in UI
on_user_transcript→ Final user text, trigger AI response
on_tts_request    → AI wants to speak, play audio
```

### Session Broadcasting

For ACS calls, the phone WebSocket is separate from the dashboard WebSocket.
Use `broadcast_only=True` to reach all session connections:

```python
# ✅ Correct - broadcasts to dashboard relay
await send_user_transcript(ws, text, session_id=sid, broadcast_only=True)

# ❌ Wrong - tries to send to ACS WebSocket directly  
await send_user_transcript(ws, text)  # broadcast_only defaults to False
```

## Common Tasks

### Adding a new UI message type

1. Create envelope in `src/ws_helpers/envelopes.py`
2. Call `broadcast_session_envelope()` with `broadcast_only=True`
3. Handle in frontend `App.jsx` message handler

### Modifying TTS behavior

1. Look at `_send_tts_acs()` or `_send_tts_browser()` in `media_handler.py`
2. TTS audio generation is in `src/ws_helpers/shared_ws.py`

### Changing barge-in behavior

1. Core detection in `SpeechCascadeHandler._detect_barge_in()` (in `voice_channels/`)
2. Handler response in `MediaHandler._on_barge_in()`

## Testing

```bash
# Run handler tests
pytest tests/test_acs_media_lifecycle.py -v
```

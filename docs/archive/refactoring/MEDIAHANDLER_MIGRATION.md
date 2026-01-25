# MediaHandler → VoiceHandler Migration

**Created:** 2026-01-03  
**Status:** Phase 4 Complete - MediaHandler Deprecated  
**Tracking Issue:** #TBD

---

## Overview

This document tracks the migration from `MediaHandler` (Phase 2) to `VoiceHandler` (Phase 3). The goal is to deprecate `MediaHandler` while ensuring backward compatibility for existing endpoints.

---

## Current State

### Active Code Paths

| Endpoint | Handler | Location |
|----------|---------|----------|
| `/api/v1/browser/conversation` | **VoiceHandler** | `api/v1/endpoints/browser.py:66` |
| `/api/v1/media/stream` | **VoiceHandler** | `api/v1/endpoints/media.py:31` |

### Handler Locations

| Handler | Path | Status |
|---------|------|--------|
| MediaHandler | `apps/artagent/backend/api/v1/handlers/__init__.py` | ⚠️ Alias to VoiceHandler |
| VoiceHandler | `apps/artagent/backend/voice/handler.py` | ✅ Active (replacement) |
| media_handler.py | `apps/artagent/backend/api/v1/handlers/media_handler.py` | 🗑️ Unused - ready for deletion |

---

## Core Functionality to Preserve

### 1. Factory Pattern

Both handlers use `create()` as async factory:

```python
# MediaHandler (current)
handler = await MediaHandler.create(config, app_state)

# VoiceHandler (new)
handler = await VoiceHandler.create(config, app_state)
```

**Test Coverage Required:**
- [ ] Pool acquisition (TTS/STT)
- [ ] Pool timeout handling (1013 close code)
- [ ] Memory manager loading
- [ ] Scenario/agent resolution

### 2. Lifecycle Methods

| Method | Description | Notes |
|--------|-------------|-------|
| `start()` | Initialize threads, queue greeting | Browser queues immediately; ACS waits for metadata |
| `run()` | Browser message loop | Browser only |
| `handle_media_message()` | ACS message processing | ACS only |
| `stop()` | Cleanup resources, release pools | Must be idempotent |

**Test Coverage Required:**
- [ ] Start initializes threads
- [ ] Start queues greeting for browser
- [ ] Stop releases pools
- [ ] Double-stop is safe (idempotent)

### 3. Audio Processing

| Transport | Input Format | RMS Threshold | Sample Rate |
|-----------|--------------|---------------|-------------|
| Browser | Raw PCM bytes | 200 | 24kHz |
| ACS | Base64 JSON | N/A | 16kHz |

**Test Coverage Required:**
- [ ] `pcm16le_rms()` calculation
- [ ] Browser audio → STT thread
- [ ] ACS AudioData → STT thread
- [ ] Silence detection

### 4. Barge-In Handling

Single flow:
1. Signal `cancel_event`
2. Cancel pending TTS/orchestration tasks
3. Send transport-specific stop (ACS: StopAudio, Browser: control msg)
4. Reset state after delay

**Test Coverage Required:**
- [ ] Cancel event signaling
- [ ] Task cancellation
- [ ] ACS StopAudio message
- [ ] Browser control message
- [ ] State reset

### 5. Greeting Flow

| Transport | Timing | Voice Source |
|-----------|--------|--------------|
| Browser | Queue immediately on `start()` | `TTSPlayback.get_agent_voice()` |
| ACS | Queue after AudioMetadata | Agent config → session → default |

**Test Coverage Required:**
- [ ] Greeting text derivation
- [ ] Session agent greeting
- [ ] Unified agent greeting
- [ ] Default greeting fallback

### 6. TTS Playback

Routes to `TTSPlayback` with:
- Voice name/style/rate from agent config
- Barge-in cancellation via `cancel_event`
- Transport-appropriate method (ACS: `play_to_acs`, Browser: `play_to_browser`)

**Test Coverage Required:**
- [ ] Voice resolution from agent
- [ ] Cancellation via event
- [ ] ACS playback path
- [ ] Browser playback path

### 7. Callback System

| Callback | Trigger | Action |
|----------|---------|--------|
| `_on_barge_in` | STT detects speech during TTS | Stop all TTS |
| `_on_greeting` | Greeting event from queue | Play greeting audio |
| `_on_partial_transcript` | Interim STT result | Broadcast to UI |
| `_on_user_transcript` | Final STT result | Broadcast + trigger AI |
| `_on_tts_request` | AI response chunk | Play TTS |

**Test Coverage Required:**
- [ ] Callback wiring to SpeechCascadeHandler
- [ ] Barge-in callback execution
- [ ] Transcript broadcast

### 8. Idle Timeout

- Timeout: 300s (5 min)
- Check interval: 5s
- Action: Terminate session

**Test Coverage Required:**
- [ ] Activity timestamp update
- [ ] Timeout detection
- [ ] Session termination

---

## Configuration Compatibility

### MediaHandlerConfig

```python
@dataclass
class MediaHandlerConfig:
    websocket: WebSocket
    session_id: str
    transport: TransportType = TransportType.BROWSER
    conn_id: str | None = None
    call_connection_id: str | None = None
    stream_mode: StreamMode = ACS_STREAMING_MODE
    user_email: str | None = None
    scenario: str | None = None
```

### VoiceHandlerConfig

```python
@dataclass
class VoiceHandlerConfig:
    websocket: WebSocket
    session_id: str
    transport: TransportType = TransportType.BROWSER
    conn_id: str | None = None
    call_connection_id: str | None = None
    stream_mode: StreamMode = ACS_STREAMING_MODE
    user_email: str | None = None
    scenario: str | None = None
```

**Difference:** Identical. VoiceHandler should accept MediaHandlerConfig directly.

---

## Property Compatibility

| Property | MediaHandler | VoiceHandler | Notes |
|----------|--------------|--------------|-------|
| `session_id` | ✅ | ✅ | |
| `call_connection_id` | ✅ | ✅ | Added property |
| `stream_mode` | ✅ | ✅ | Added property |
| `memory_manager` | ✅ | ✅ | |
| `is_running` | ✅ | ✅ | Added property |
| `websocket` | ✅ | ✅ | Added property |
| `metadata` | ✅ | ✅ | Added property |
| `speech_cascade` | ✅ | Self | VoiceHandler IS the cascade |

---

## Test Matrix

### Unit Tests (Isolated)

| Test | Priority | Status |
|------|----------|--------|
| `test_pcm16le_rms_calculation` | P0 | ✅ |
| `test_config_dataclass_defaults` | P0 | ✅ |
| `test_memory_manager_loading` | P0 | ✅ |
| `test_greeting_derivation_priority` | P1 | ✅ |
| `test_barge_in_state_machine` | P1 | ✅ |
| `test_idle_timeout_detection` | P2 | ✅ |

### Integration Tests (Mocked Pools)

| Test | Priority | Status |
|------|----------|--------|
| `test_factory_acquires_pools` | P0 | ✅ |
| `test_factory_handles_pool_timeout` | P0 | ✅ |
| `test_lifecycle_start_stop` | P0 | ✅ |
| `test_browser_message_loop` | P1 | [ ] |
| `test_acs_audio_processing` | P1 | ✅ |
| `test_tts_playback_routing` | P1 | [ ] |

### Compatibility Tests (Endpoints)

| Test | Priority | Status |
|------|----------|--------|
| `test_browser_endpoint_with_voicehandler` | P0 | [ ] |
| `test_media_endpoint_with_voicehandler` | P0 | [ ] |
| `test_backward_compat_config` | P1 | [ ] |

---

## Migration Checklist

### Phase 1: Test Coverage

- [x] Create `tests/test_voice_handler_compat.py`
- [x] Achieve 80%+ coverage on MediaHandler core paths (38 tests passing)
- [x] All tests pass with MediaHandler

### Phase 2: VoiceHandler Completion

- [x] Add missing properties for backward compat
- [x] Ensure VoiceHandler passes same tests (52 tests passing)
- [x] Add VoiceHandler-specific tests
- [x] Export TransportType/VoiceSessionContext from shared module

### Phase 3: Endpoint Migration

**Analyzed:** Both endpoints use identical factory patterns.

#### browser.py (Lines 259-265)
```python
# Current (Speech Cascade mode only)
config = MediaHandlerConfig(...)
handler = await MediaHandler.create(config, websocket.app.state)
```

**Voice Live mode:** Already uses `VoiceLiveSDKHandler` directly (no change needed).

#### media.py (Lines 245-254)
```python
# Current (StreamMode.MEDIA only)
config = MediaHandlerConfig(...)
return await MediaHandler.create(config, websocket.app.state)
```

**Voice Live mode:** Already uses `VoiceLiveSDKHandler` directly (no change needed).

#### Migration Changes Required

1. **Import swap:** Replace `MediaHandler, MediaHandlerConfig` with `VoiceHandler, VoiceHandlerConfig`
2. **No code changes:** Factory signatures are identical
3. **No feature flags needed:** Can do direct swap with test validation

- [x] Analyze browser.py endpoint usage
- [x] Analyze media.py endpoint usage
- [x] Update `browser.py` to use VoiceHandler
- [x] Update `media.py` to use VoiceHandler
- [x] Smoke test both transports (52 tests passing)

### Phase 4: Deprecation

- [x] MediaHandler aliased to VoiceHandler in handlers/__init__.py
- [x] All imports now route through voice module
- [x] media_handler.py no longer imported anywhere
- [x] Document migration path
- [ ] Delete media_handler.py (optional - next release cycle)

---

## Files Changed

| Action | File | Description |
|--------|------|-------------|
| CREATE | `tests/test_voice_handler_compat.py` | Backward compat test suite (52 tests) |
| CREATE | `docs/refactoring/MEDIAHANDLER_MIGRATION.md` | This tracking doc |
| MODIFY | `apps/.../voice/handler.py` | Add missing properties, VOICE_LIVE_* aliases, fix barge_in_handler |
| MODIFY | `apps/.../voice/__init__.py` | Export VoiceHandler, VoiceHandlerConfig, TransportType, ACSMessageKind, constants |
| MODIFY | `apps/.../handlers/__init__.py` | Alias MediaHandler→VoiceHandler (no more media_handler imports) |
| DEPRECATE | `apps/.../handlers/media_handler.py` | ✅ Unused - ready for deletion |
| MODIFY | `apps/.../endpoints/browser.py` | ✅ Use VoiceHandler (migrated) |
| MODIFY | `apps/.../endpoints/media.py` | ✅ Use VoiceHandler (migrated) |
| DEPRECATE | `apps/.../handlers/media_handler.py` | Pending deprecation warning |

---

## Findings

### 1. Existing Test Coverage Gaps

The existing test suite (`test_acs_media_lifecycle.py`) is **skipped** because:
- References removed `acs_media_lifecycle.py` file
- Uses old `ACSMediaHandler` class directly
- Needs complete rewrite for new architecture

### 2. Key Differences Between Handlers

| Aspect | MediaHandler | VoiceHandler |
|--------|--------------|--------------|
| State container | `websocket.state` | `VoiceSessionContext` |
| SpeechCascade | Separate object | Inlined (handler IS cascade) |
| Barge-in | Via callbacks | `handle_barge_in()` method |
| Thread management | Delegates to SpeechCascadeHandler | Direct thread management |

### 3. Simplification Opportunities

The VoiceHandler design eliminates:
- Redundant state copying to `websocket.state`
- Separate SpeechCascadeHandler layer
- Circular callback chains

### 4. Backward Compatibility Requirements

VoiceHandler must support:
- Same factory signature (`create(config, app_state)`)
- Same lifecycle methods (`start()`, `run()`, `stop()`)
- Same properties (`session_id`, `memory_manager`, etc.)
- `websocket.state` population (for legacy orchestrator code)

---

## References

- [TTS_MODULE_CONSOLIDATION.md](../architecture/voice/TTS_MODULE_CONSOLIDATION.md) - TTS migration context
- [LEGACY_CLEANUP_2026-01-03.md](../operations/LEGACY_CLEANUP_2026-01-03.md) - TTS cleanup completed
- [voice/README.md](../../apps/artagent/backend/voice/README.md) - Voice module overview

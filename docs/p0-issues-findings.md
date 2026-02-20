# P0 Issue Validation Findings

> **Date:** 2026-02-13
> **Test file:** `tests/test_p0_issue_validation.py`
> **Result:** **35/35 tests PASS** — all 6 P0 issues confirmed present in codebase

---

## How to Use This Document

Each P0 issue below has:
- **Status**: CONFIRMED (issue exists) or RESOLVED (fix verified)
- **Evidence**: Test class + specific assertions that prove the issue
- **Fix guidance**: What to change — designed so fixing the issue makes the test FAIL
- **Risk**: What happens if left unfixed

When fixing an issue, run the tests — the relevant tests should **fail** with messages starting with `FIX DETECTED:`, confirming the fix was applied. Then update the status here.

```bash
python -m pytest tests/test_p0_issue_validation.py -v
```

---

## Summary

| ID | Issue | Status | Tests | Severity |
|----|-------|--------|-------|----------|
| P0-1 | Synchronous SDK calls blocking event loop | **CONFIRMED** | 9 tests | Critical — all-user latency |
| P0-2 | Shared mutable SpeechConfig race condition | **CONFIRMED** | 4 tests | Critical — wrong voice output |
| P0-3 | asyncio.Event called from wrong thread | **CONFIRMED** | 5 tests | Critical — barge-in crashes |
| P0-4 | CORS wildcard + auth disabled by default | **CONFIRMED** | 4 tests | Critical — full API exposure |
| P0-5 | TTS lock deadlock under barge-in | **CONFIRMED** | 3 tests | Critical — broken interruption |
| P0-6 | Auth tokens / secrets logged at INFO | **CONFIRMED** | 5 tests | Critical — credential exposure |

---

## P0-1: Synchronous SDK Calls Blocking the Event Loop

**Status:** CONFIRMED
**Test class:** `TestP0_1_SyncBlockingCalls` (9 tests)

### What We Found

| File | Method(s) | Blocking Call | Impact |
|------|-----------|---------------|--------|
| `src/aoai/manager.py` | `async_generate_chat_completion_response`, `generate_chat_response_o1`, `generate_chat_response_no_history`, `generate_chat_response`, `generate_response` | `self.openai_client.chat.completions.create()` (sync) | Blocks event loop 500ms-10s per LLM call |
| `src/aoai/manager.py` | Streaming loops | `time.sleep(0.01)` / `time.sleep(0.001)` | Blocks event loop during streaming |
| `src/cosmosdb/manager.py` | `insert_document`, `upsert_document`, `read_document`, `query_documents`, `document_exists`, `delete_document` | Synchronous `pymongo` calls (all `def`, not `async def`) | Blocks event loop 1-100ms per DB operation |
| `src/acs/email_service.py` | `EmailService.send_email` | `self.client.begin_send()` + `poller.result()` | Blocks event loop for full email send (seconds) |
| `src/acs/sms_service.py` | `SmsService.send_sms` | `sms_client.send()` + new `SmsClient` per call | Blocks event loop + 50-200ms client creation overhead |

### Evidence

- `AzureOpenAIManager.__init__` creates `AzureOpenAI` (sync client), not `AsyncAzureOpenAI`
- 5 async methods call `self.openai_client.chat.completions.create()` without `run_in_executor` or `asyncio.to_thread`
- `time.sleep()` (blocking) used instead of `await asyncio.sleep()`
- All 6 CosmosDB methods are plain `def` (synchronous)
- Both Email and SMS services wrap sync SDK calls in `async def` without executor

### Risk

Every concurrent voice session shares the same event loop. A single LLM call (500ms-10s) blocks ALL other sessions' audio processing, causing:
- STT recognition delays (missed speech)
- TTS output stalling (silence gaps)
- WebSocket timeouts (dropped calls)

### Fix Guidance

**Option A (preferred):** Switch to async SDK clients
```python
# Before
from openai import AzureOpenAI
self.openai_client = AzureOpenAI(...)

# After
from openai import AsyncAzureOpenAI
self.openai_client = AsyncAzureOpenAI(...)
# Change all .create() calls to await
```

**Option B (quick fix):** Wrap sync calls in `asyncio.to_thread()`
```python
# Before
response = self.openai_client.chat.completions.create(...)

# After
response = await asyncio.to_thread(
    self.openai_client.chat.completions.create, ...
)
```

**For CosmosDB:** Switch to `motor` (async pymongo) or wrap all operations in `asyncio.to_thread()`.

---

## P0-2: Shared Mutable SpeechConfig Race Condition

**Status:** CONFIRMED
**Test class:** `TestP0_2_SpeechConfigRace` (4 tests)

### What We Found

`SpeechSynthesizer` stores a shared `self.cfg` (`SpeechConfig`) object. At least **6 methods** do:

```python
speech_config = self.cfg                              # Reference, NOT copy
speech_config.speech_synthesis_language = self.language  # Mutates shared object
speech_config.speech_synthesis_voice_name = voice        # Mutates shared object
speech_config.set_speech_synthesis_output_format(...)    # Mutates shared object
```

Found at lines: 1037, 1378, 1452, 1596, 1826, 1917

The `_synth_semaphore = asyncio.Semaphore(4)` is a **class-level** variable shared across ALL instances, artificially limiting global concurrency to 4 regardless of pool size.

### Evidence

- `speech_config = self.cfg` is a reference assignment, not a deep copy (confirmed: no `copy.deepcopy` usage)
- 3+ mutation sites found immediately after the reference assignment
- No `asyncio.Lock` or `threading.Lock` protects the mutation sections
- Class docstring claims "No shared mutable state between synthesis calls" — contradicted by the code

### Risk

When pooled `SpeechSynthesizer` instances serve multiple concurrent sessions:
- Session A's voice setting leaks to Session B's synthesis
- Audio format mismatches cause garbled output or silent failures
- The issue is intermittent and hard to reproduce — it depends on task interleaving

### Fix Guidance

```python
# Before (reference to shared object)
speech_config = self.cfg
speech_config.speech_synthesis_voice_name = voice

# After (create new config per synthesis call)
speech_config = self._create_speech_config()
speech_config.speech_synthesis_voice_name = voice
```

Or use a lock if config creation is expensive:
```python
async with self._cfg_lock:
    self.cfg.speech_synthesis_voice_name = voice
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.cfg, ...)
```

---

## P0-3: asyncio.Event Called from Non-Event-Loop Threads

**Status:** CONFIRMED
**Test class:** `TestP0_3_AsyncioEventThreadSafety` (5 tests)

### What We Found

`VoiceSessionContext` at `apps/artagent/backend/voice/shared/context.py`:

```python
cancel_event: asyncio.Event = field(default_factory=asyncio.Event)  # line 173

def request_cancel(self) -> None:     # line 252
    self.cancel_event.set()           # line 258 — called from Speech SDK threads!
    self.tts_cancel_requested = True

def clear_cancel(self) -> None:       # line ~265
    self.cancel_event.clear()         # line 267 — also from threads
```

### Evidence

- `cancel_event` is `asyncio.Event` (not `threading.Event`)
- `request_cancel()` calls `.set()` directly — no `call_soon_threadsafe()`
- Class docstring claims "Thread Safety: The cancel_event and boolean flags are safe to access from multiple threads" — this is false for `asyncio.Event`
- [CPython docs](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event): "This class is not thread safe."

### Risk

Speech SDK runs callbacks on its own threads. When `request_cancel()` is called from a Speech SDK thread:
- `asyncio.Event.set()` may corrupt internal waiters list
- `await cancel_event.wait()` on the event loop may never wake up
- Can cause deadlocks, missed barge-in events, or event loop crashes

### Fix Guidance

**Option A:** Use `loop.call_soon_threadsafe()`
```python
def request_cancel(self) -> None:
    if self.event_loop and self.event_loop.is_running():
        self.event_loop.call_soon_threadsafe(self.cancel_event.set)
    self.tts_cancel_requested = True
```

**Option B:** Use `threading.Event` for cross-thread signaling + bridge to asyncio
```python
_thread_cancel: threading.Event = field(default_factory=threading.Event)

async def wait_for_cancel(self, timeout: float) -> bool:
    return await asyncio.to_thread(self._thread_cancel.wait, timeout)
```

---

## P0-4: CORS Wildcard + Auth Disabled by Default

**Status:** CONFIRMED
**Test class:** `TestP0_4_CORSAndAuthDefaults` (4 tests)

### What We Found

`apps/artagent/backend/config/settings.py`:

```python
ALLOWED_ORIGINS: list[str] = _env_list("ALLOWED_ORIGINS", "*")     # line 406
ENABLE_AUTH_VALIDATION: bool = _env_bool("ENABLE_AUTH_VALIDATION", False)  # line 376
```

### Evidence

- `ALLOWED_ORIGINS` defaults to literal `"*"` — all origins allowed
- `ENABLE_AUTH_VALIDATION` defaults to `False` — no request authentication
- No runtime guard prevents these defaults in production environments
- Combined effect: **any website on the internet can call every API endpoint**

### Risk

An attacker can:
1. Call `PUT /api/v1/health/agents/{name}` to modify agent system prompts (prompt injection)
2. Access session data, call recordings, and customer PII
3. Initiate outbound ACS calls through the platform
4. Exfiltrate voice transcripts from active sessions

### Fix Guidance

**Immediate:** Change defaults for production safety
```python
# Fail-closed: no CORS origins allowed by default
ALLOWED_ORIGINS: list[str] = _env_list("ALLOWED_ORIGINS", "")

# Fail-closed: auth required by default
ENABLE_AUTH_VALIDATION: bool = _env_bool("ENABLE_AUTH_VALIDATION", True)
```

**Better:** Add an environment guard
```python
_env = os.getenv("ENVIRONMENT", "development")
if _env in ("production", "staging") and ALLOWED_ORIGINS == ["*"]:
    raise ValueError("ALLOWED_ORIGINS must be explicitly set in production")
```

---

## P0-5: TTS Lock Deadlock Under Barge-In

**Status:** CONFIRMED
**Test class:** `TestP0_5_TTSLockDeadlock` (3 tests)

### What We Found

`apps/artagent/backend/voice/tts/playback.py`:

```python
async def play_to_browser(self, text, ...):
    async with self._tts_lock:               # Lock acquired HERE
        if self._cancel_event.is_set():       # Cancel check (too late)
            self._cancel_event.clear()
            return False
        self._is_playing = True
        synth, tier = await self._app_state.tts_pool.acquire_for_session(...)
        pcm_bytes = await self._synthesize(synth, text, ...)  # 100-500ms
        return await self._stream_to_browser(pcm_bytes, ...)  # 200ms-2s
```

The `_tts_lock` is held from before synthesis through the end of audio streaming. Both `play_to_browser` and `play_to_acs` follow this pattern.

### Evidence

- `async with self._tts_lock:` wraps **both** `_synthesize()` and `_stream_to_browser()`/`_stream_to_acs()`
- Cancel event is checked only **after** acquiring the lock
- Test `test_lock_blocks_concurrent_speak_calls` proves: a concurrent caller must wait for the full synthesis+streaming duration (250ms+ measured) before the lock is available
- No periodic cancel check during the streaming phase

### Risk

When user speaks during AI response (barge-in):
1. `request_cancel()` is called → sets `cancel_event`
2. The current `play_to_browser` holds `_tts_lock` for the remaining streaming duration
3. The orchestrator's **next** `speak()` call (to acknowledge the user) blocks on the lock
4. User perceives 0.5-3s delay after speaking before getting a response
5. For a "real-time voice" system, this destroys the conversation flow

### Fix Guidance

**Split the lock scope:**
```python
async def play_to_browser(self, text, ...):
    async with self._tts_lock:
        synth, tier = await self._app_state.tts_pool.acquire_for_session(...)
        pcm_bytes = await self._synthesize(synth, text, ...)
    # Lock RELEASED before streaming — allows preemption
    if self._cancel_event.is_set():
        return False
    return await self._stream_to_browser(pcm_bytes, ...)
```

**Or use a cancellable streaming loop:**
```python
async def _stream_to_browser(self, pcm_bytes, ...):
    for chunk in chunk_audio(pcm_bytes):
        if self._cancel_event.is_set():
            return False  # Abort mid-stream
        await ws.send_bytes(chunk)
```

---

## P0-6: Auth Tokens and Secrets Logged at INFO Level

**Status:** CONFIRMED
**Test class:** `TestP0_6_SecretLogging` (5 tests)

### What We Found

**File 1: `apps/artagent/backend/api/v1/endpoints/calls.py` (line 742)**
```python
logger.info(f"   Headers: {dict(http_request.headers)}")
```
Logs **all** HTTP headers at INFO level, including:
- `Authorization: Bearer <token>`
- `x-ms-client-principal` (B2C tokens)
- `Cookie` headers
- ACS authentication tokens

**File 1 continued (line 753):**
```python
logger.info(f"📦 Callback payload: {events_data}")
```
Logs the entire ACS callback payload which may contain caller IDs and PII.

**File 2: `src/aoai/client.py` (line 186-192)**
```python
azure_vars = {
    k: v[:50] + "..." if len(v) > 50 else v
    for k, v in os.environ.items()
    if k.startswith("AZURE_")
}
logger.error("AZURE_OPENAI_ENDPOINT not available. Azure env vars: %s", azure_vars)
```
Logs all `AZURE_*` environment variables truncated to 50 chars. Most API keys are 32 chars — **fully exposed**.

### Evidence

- Header logging at INFO level (not DEBUG) — appears in ALL production log outputs
- 50-char truncation insufficient for 32-char API keys
- Payload logging at INFO level includes full event data
- No allowlist/blocklist for safe vs. sensitive headers

### Risk

In production with Azure Monitor / Application Insights:
- API keys persisted in queryable Log Analytics tables (90-day retention by default)
- Bearer tokens enable session impersonation
- Compliance violations (SOC2, GDPR, HIPAA) for PII in logs
- Single credential leak can compromise Azure OpenAI, Speech, and ACS services

### Fix Guidance

**For headers — allowlist safe headers:**
```python
SAFE_HEADERS = {"content-type", "x-ms-call-connection-id", "user-agent"}
safe = {k: v for k, v in http_request.headers.items() if k.lower() in SAFE_HEADERS}
logger.debug("Callback headers: %s", safe)  # Change to DEBUG
```

**For env vars — never log values:**
```python
azure_var_names = [k for k in os.environ if k.startswith("AZURE_")]
logger.error("AZURE_OPENAI_ENDPOINT not set. Defined AZURE_* vars: %s", azure_var_names)
```

**For payloads — redact or move to DEBUG:**
```python
logger.debug("Callback payload: %s", events_data)  # DEBUG, not INFO
```

---

## Recommended Fix Order

| Priority | Issue | Effort | Why First |
|----------|-------|--------|-----------|
| 1 | **P0-6** Secret logging | ~1 hour | Immediate credential exposure risk — smallest effort, highest security ROI |
| 2 | **P0-4** CORS + auth defaults | ~1 hour | Change 2 default values + add env guard |
| 3 | **P0-1** Sync blocking (AOAI) | ~2 hours | Largest user-facing perf impact — switch to `AsyncAzureOpenAI` |
| 4 | **P0-3** Thread-unsafe cancel event | ~2 hours | Use `call_soon_threadsafe` in `request_cancel`/`clear_cancel` |
| 5 | **P0-2** SpeechConfig race | ~2 hours | Create new config per synthesis call or add lock |
| 6 | **P0-5** TTS lock scope | ~3 hours | Requires careful redesign of cancel/stream interaction |
| 7 | **P0-1** Sync blocking (CosmosDB) | ~4 hours | Switch to `motor` or wrap all methods in `to_thread()` |
| 8 | **P0-1** Sync blocking (Email/SMS) | ~1 hour | Wrap `begin_send`/`send` in `asyncio.to_thread()` |

---

## Verification

After applying fixes, run:
```bash
python -m pytest tests/test_p0_issue_validation.py -v
```

Fixed tests should **FAIL** with assertion messages starting with `FIX DETECTED:`. Update the test assertions to reflect the new expected behavior, then update this document's status column.

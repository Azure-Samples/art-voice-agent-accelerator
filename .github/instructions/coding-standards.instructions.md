---
applyTo: "**/*.py"
---

# Coding Standards

This document describes the coding standards and conventions for the Real-Time Voice Agent Accelerator project.

---

## Key Modules to Reuse

Before writing new code, check if these modules already solve your problem:

| Need | Use | Never Do |
|------|-----|----------|
| Logging | `from utils.ml_logging import get_logger` | `import logging` |
| Configuration | `from config.settings import X` | `os.getenv()` |
| Redis | `src/redis/manager.py` | Direct redis client |
| Azure OpenAI | `src/aoai/` | Raw `openai` client |
| Speech TTS/STT | `src/speech/` | Direct Speech SDK |
| Connection pools | `src/pools/` | Creating new clients per request |
| Agents | `registries/agentstore/base.py` → `UnifiedAgent` | Custom agent classes |
| Tools | `registries/toolstore/` | Inline tool definitions |
| Pydantic models | Extend `api/v1/models/base.py` | Raw dicts |

---

## Anti-Patterns (Never Do)

| Anti-Pattern | Why It's Bad | Do This Instead |
|--------------|--------------|-----------------|
| Global singletons | Thread-unsafe, hard to test | Module-level functions |
| Factory classes | Over-engineering | Simple functions |
| Abstract base classes (single impl) | Unnecessary abstraction | Concrete class |
| `logging.getLogger()` | Misses custom levels, formatting | `get_logger(__name__)` |
| `os.getenv()` | Bypasses validation, defaults | `config.settings` |
| `requests` library | Blocks async event loop | `aiohttp` or `httpx` |
| Creating clients per request | 100-500ms latency hit | Use `src/pools/` |

---

## Code Style and Formatting

We use `black`, `isort`, and `ruff` for formatting and linting with the following configuration:

| Setting | Value |
|---------|-------|
| Line length | 100 characters |
| Target Python | 3.11+ |
| Docstrings | Google-style |

Run formatters before committing:
```bash
make format  # or: black . && isort .
```

---

## Function Parameter Guidelines

To make code easier to use and maintain:

### Positional Parameters
Only use for **up to 3 fully expected parameters**:
```python
# ✅ Good - 3 or fewer positional args
def process_audio(audio_data: bytes, sample_rate: int, channels: int) -> AudioResult:
    ...

# ❌ Bad - too many positional args
def process_audio(audio_data, sample_rate, channels, format, bitrate, codec):
    ...
```

### Keyword-Only Parameters
Use `*` to force keyword arguments for optional/configuration parameters:
```python
# ✅ Good - keyword-only after *
async def create_agent(
    name: str,
    *,
    voice: str = "en-US-JennyNeural",
    temperature: float = 0.7,
    timeout: float | None = None,
) -> Agent:
    ...

# Usage is self-documenting:
agent = await create_agent("support", voice="en-US-GuyNeural", temperature=0.9)
```

### Avoid Requiring User Imports
Provide string-based overrides when applicable:
```python
# ❌ Forces user to import enum
from src.enums.modes import AudioFormat
def encode_audio(data: bytes, format: AudioFormat) -> bytes: ...

# ✅ Accepts string or enum - no import needed
def encode_audio(
    data: bytes,
    format: Literal["pcm16", "opus", "mp3"] | AudioFormat = "pcm16"
) -> bytes:
    if isinstance(format, str):
        format = AudioFormat(format)
    ...
```

### Document kwargs Explicitly
Always document how `**kwargs` are used:
```python
async def create_client(
    endpoint: str,
    *,
    client_kwargs: dict[str, Any] | None = None,
    **request_kwargs: Any,
) -> Client:
    """Create a new client.

    Args:
        endpoint: The service endpoint URL.

    Keyword Args:
        client_kwargs: Passed to the underlying HTTP client constructor.
        request_kwargs: Passed to each request (headers, timeout, etc.).
    """
```

### Separate kwargs by Purpose
Don't mix everything in `**kwargs`:
```python
# ❌ Ambiguous - what does kwargs configure?
def connect(url: str, **kwargs): ...

# ✅ Clear separation of concerns
def connect(
    url: str,
    *,
    connection_kwargs: dict[str, Any] | None = None,
    auth_kwargs: dict[str, Any] | None = None,
): ...
```

---

## Asynchronous Programming

**Assume everything is async.** This is a real-time voice system where blocking kills latency.

### Rules
1. All I/O operations **must** be `async`
2. Never use blocking calls (`time.sleep`, `requests`, synchronous file I/O)
3. Use explicit timeouts on all awaits
4. Handle cancellation gracefully

### Patterns
```python
# ✅ Explicit timeout - never hang forever
result = await asyncio.wait_for(
    external_service.call(),
    timeout=5.0
)

# ✅ Background task with proper lifecycle
task = asyncio.create_task(background_processor())
try:
    await main_logic()
finally:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

# ✅ Concurrent operations
results = await asyncio.gather(
    fetch_user(user_id),
    fetch_settings(user_id),
    return_exceptions=True,
)

# ❌ Never do this - blocks the event loop
time.sleep(1)  # Use: await asyncio.sleep(1)
requests.get(url)  # Use: await aiohttp or httpx
```

### HTTP Clients
```python
# ❌ Blocking - never use
import requests
response = requests.get(url)

# ✅ Async - always use
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# ✅ Or httpx
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

---

## Attributes vs Inheritance

Prefer composition over inheritance when parameters are mostly the same:

```python
# ✅ Preferred - single class with type attribute
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

user_msg = ChatMessage(role="user", content="Hello")
asst_msg = ChatMessage(role="assistant", content="Hi there!")

# ❌ Unnecessary inheritance hierarchy
class UserMessage(BaseModel):
    content: str

class AssistantMessage(BaseModel):
    content: str
```

### When to Use Inheritance
- Significantly different behavior (not just different field values)
- Need polymorphic dispatch
- Implementing protocols/interfaces

---

## Logging

Use the centralized logging system:

```python
# ✅ Always use this
from utils.ml_logging import get_logger

logger = get_logger(__name__)

# Use appropriate levels
logger.debug("Detailed trace info")
logger.info("Normal operation")
logger.keyinfo("Important business event")  # Custom level
logger.warning("Something unexpected but recoverable")
logger.error(f"Operation failed: {e}")

# ❌ Never use direct logging
import logging
logger = logging.getLogger(__name__)
```

### Logging Best Practices
```python
# ✅ Log before raising
try:
    result = await risky_operation()
except SomeError as e:
    logger.error(f"Operation failed for user {user_id}: {e}")
    raise

# ✅ Structured logging for observability
logger.info(
    "Call completed",
    extra={
        "call_id": call_id,
        "duration_ms": duration,
        "agent": agent_name,
    }
)

# ❌ Don't log sensitive data
logger.info(f"User credentials: {password}")  # Never!
```

---

## Configuration

Always use the config module, never raw environment variables:

```python
# ✅ Correct
from config.settings import AZURE_OPENAI_ENDPOINT, TTS_SAMPLE_RATE

# ❌ Wrong - bypasses config validation and defaults
import os
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
```

### Why This Matters
- Config module handles defaults
- Validates required values at startup
- Integrates with Azure App Configuration
- Single source of truth

---

## Type Hints

Full type hints on all public functions and methods:

```python
# ✅ Complete type hints
async def process_audio(
    audio_data: bytes,
    sample_rate: int,
    *,
    format: Literal["pcm16", "opus"] = "pcm16",
    callback: Callable[[bytes], None] | None = None,
) -> AudioResult:
    ...

# Modern union syntax (Python 3.10+)
def get_user(user_id: str) -> User | None:  # Not Optional[User]
    ...

# Use TypeVar for generics
T = TypeVar("T")

async def retry_async(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
) -> T:
    ...
```

### Type Hint Rules
| Pattern | Use | Avoid |
|---------|-----|-------|
| Optional | `str \| None` | `Optional[str]` |
| Union | `int \| str` | `Union[int, str]` |
| Collections | `list[str]` | `List[str]` |
| Dicts | `dict[str, Any]` | `Dict[str, Any]` |

---

## Functions Over Classes

Prefer functions unless you genuinely need state:

```python
# ✅ Preferred - simple function
async def transcribe_audio(audio: bytes, language: str = "en-US") -> str:
    client = get_speech_client()
    return await client.recognize(audio, language)

# ❌ Unnecessary class wrapper
class AudioTranscriber:
    def __init__(self, language: str = "en-US"):
        self.language = language
        self.client = get_speech_client()

    async def transcribe(self, audio: bytes) -> str:
        return await self.client.recognize(audio, self.language)
```

### Anti-Patterns to Avoid
- Factory classes when a function suffices
- Adapter/Facade/Manager wrappers around existing services
- Abstract base classes for single implementations
- Singletons (use module-level functions instead)

---

## Error Handling

### Use Specific Exceptions
```python
# ✅ Specific, actionable exceptions
class AgentNotFoundError(Exception):
    """Raised when an agent configuration cannot be found."""
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"Agent not found: {agent_name}")

# ✅ HTTP exceptions for API layer
from fastapi import HTTPException

async def get_agent(agent_id: str) -> Agent:
    agent = await load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent
```

### Retry with Tenacity
```python
from tenacity import retry, stop_after_attempt, wait_exponential

# ✅ Use tenacity for retries (already in deps)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def call_external_service():
    ...

# ❌ Don't write custom retry loops
for attempt in range(3):  # Use tenacity instead
    try:
        return await call_service()
    except Exception:
        await asyncio.sleep(2 ** attempt)
```

### Graceful Degradation
```python
# ✅ Degrade gracefully, don't crash
async def get_user_context(user_id: str) -> UserContext:
    try:
        return await fetch_full_context(user_id)
    except ExternalServiceError as e:
        logger.warning(f"Context service unavailable: {e}, using defaults")
        return UserContext.default()
```

---

## Documentation

### Google-Style Docstrings
```python
async def create_voice_session(
    call_id: str,
    agent_name: str,
    *,
    voice: str | None = None,
    context: dict[str, Any] | None = None,
) -> VoiceSession:
    """Create a new voice session for an incoming call.

    Initializes the agent, speech services, and session state.
    The session is automatically registered for cleanup on disconnect.

    Args:
        call_id: Unique identifier for the call (from ACS).
        agent_name: Name of the agent configuration to load.

    Keyword Args:
        voice: Override the default TTS voice.
        context: Initial context variables for the agent.

    Returns:
        Configured VoiceSession ready for audio streaming.

    Raises:
        AgentNotFoundError: If agent_name doesn't match any configuration.
        SessionLimitError: If maximum concurrent sessions reached.

    Example:
        >>> session = await create_voice_session(
        ...     call_id="abc-123",
        ...     agent_name="support",
        ...     context={"customer_tier": "premium"}
        ... )
    """
```

### When to Document
| Situation | Docstring |
|-----------|-----------|
| Public function/method | Required |
| Private function (`_name`) | Optional, only if complex |
| Obvious one-liner | One-line docstring |
| Class | Required, describe purpose |

---

## Performance Considerations

This is a **real-time audio system**. Latency matters.

### Cache Expensive Computations
```python
# ✅ Cache computed values
class AgentConfig:
    def __init__(self, yaml_path: str):
        self._yaml_path = yaml_path
        self._cached_tools: list[Tool] | None = None

    @property
    def tools(self) -> list[Tool]:
        if self._cached_tools is None:
            self._cached_tools = self._load_tools()
        return self._cached_tools

# ✅ Use functools for function memoization
from functools import lru_cache

@lru_cache(maxsize=128)
def parse_voice_config(voice_name: str) -> VoiceConfig:
    ...
```

### Prefer Attribute Access Over isinstance()
In hot paths (audio processing), type checking matters:

```python
# ✅ Fast - string/enum comparison
match message.type:
    case "audio":
        process_audio(message)
    case "text":
        process_text(message)
    case "control":
        process_control(message)

# ❌ Slower in hot paths - MRO traversal
if isinstance(message, AudioMessage):
    process_audio(message)
elif isinstance(message, TextMessage):
    process_text(message)
```

### Avoid Redundant Serialization
```python
# ✅ Compute once, reuse
serialized = message.model_dump_json()
await redis.set(key, serialized)
logger.debug(f"Stored message: {serialized}")

# ❌ Serializing twice
await redis.set(key, message.model_dump_json())
logger.debug(f"Stored message: {message.model_dump_json()}")  # Again!
```

### Connection Pooling
```python
# ✅ Reuse clients - pools are in src/pools/
from src.pools import get_tts_client, get_stt_client

client = await get_tts_client()  # Returns pooled client

# ❌ Creating new clients per request
client = SpeechClient(endpoint=ENDPOINT)  # Expensive!
```

---

## Import Structure

### Order (enforced by isort)
```python
# 1. Future imports
from __future__ import annotations

# 2. Standard library
import asyncio
import json
from typing import Any, Literal

# 3. Third-party
from fastapi import HTTPException
from pydantic import BaseModel

# 4. Local - src modules
from src.speech.tts import synthesize
from src.aoai.client import get_completion

# 5. Local - utils and config
from utils.ml_logging import get_logger
from config.settings import AZURE_OPENAI_ENDPOINT
```

### Import Rules
```python
# ✅ Explicit imports
from src.speech.tts import synthesize_speech, SpeechConfig

# ❌ Wildcard imports
from src.speech.tts import *

# ✅ Alias long module names
from apps.artagent.backend.registries.agentstore import base as agent_base

# ❌ Deep nested imports in function signatures
def process(x: apps.artagent.backend.registries.agentstore.base.Agent): ...
```

---

## Testing

### Structure
```
tests/
├── conftest.py              # Shared fixtures, mocks
├── test_<module>.py         # Unit tests mirror src/
├── evaluation/              # Agent evaluation scenarios
└── load/                    # Performance tests
```

### Patterns
```python
import pytest
from unittest.mock import AsyncMock, patch

# ✅ Async tests with pytest-asyncio
@pytest.mark.asyncio
async def test_process_audio_returns_transcript():
    audio = b"fake_audio_data"
    result = await process_audio(audio)
    assert result.transcript is not None

# ✅ Mock external services
@pytest.mark.asyncio
async def test_agent_handles_timeout():
    with patch("src.aoai.client.get_completion", new_callable=AsyncMock) as mock:
        mock.side_effect = asyncio.TimeoutError()
        result = await agent.process("hello")
        assert result.is_fallback

# ✅ Parametrize edge cases
@pytest.mark.parametrize("input,expected", [
    ("", None),
    ("hello", "hello"),
    ("  spaces  ", "spaces"),
])
def test_normalize_input(input: str, expected: str | None):
    assert normalize(input) == expected
```

---

## Telemetry

Use OpenTelemetry for observability:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# ✅ Create spans for significant operations
with tracer.start_as_current_span("process_audio") as span:
    span.set_attribute("call_id", call_id)
    span.set_attribute("agent", agent_name)
    result = await process(audio)
```

### Telemetry Rules

| Rule | Why |
|------|-----|
| One trace per `callConnectionId` | Not per audio frame (too noisy) |
| Use W3C `traceparent` propagation | Cross-service correlation |
| Span kind: `SERVER` | Inbound requests |
| Span kind: `CLIENT` | Outbound calls (Azure services) |
| Span kind: `INTERNAL` | Local processing |

### What to Trace

| Operation | Trace? | Why |
|-----------|--------|-----|
| Call lifecycle | ✅ Yes | Critical path |
| Agent handoffs | ✅ Yes | Debug routing |
| Tool executions | ✅ Yes | Performance visibility |
| Individual audio frames | ❌ No | Too noisy |
| Redis reads | ❌ No | Auto-instrumented |

---

## Security

### Never Log Secrets
```python
# ❌ NEVER
logger.info(f"Connecting with key: {api_key}")
logger.debug(f"User data: {user.dict()}")  # May contain PII

# ✅ Redact sensitive data
logger.info(f"Connecting to {endpoint}")
logger.debug(f"Processing user: {user.id}")
```

### Validate External Input
```python
# ✅ Use Pydantic for validation
from pydantic import BaseModel, Field

class CallRequest(BaseModel):
    phone_number: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$")
    agent_name: str = Field(..., min_length=1, max_length=50)

# ✅ Sanitize before use
async def process_dtmf(digits: str) -> str:
    if not digits.isdigit() or len(digits) > 20:
        raise ValueError("Invalid DTMF input")
    return digits
```

---

## Summary Checklist

Before submitting code, verify:

- [ ] All functions have type hints
- [ ] Public functions have docstrings
- [ ] No blocking I/O calls
- [ ] Using `get_logger(__name__)` not `logging.getLogger`
- [ ] Using `config.settings` not `os.getenv`
- [ ] No unnecessary class wrappers
- [ ] Timeouts on all external calls
- [ ] No secrets in logs
- [ ] Tests cover happy path and error cases
- [ ] `make format` passes

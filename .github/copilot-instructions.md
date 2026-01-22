# Copilot Guide: Real-Time Voice Apps (Python 3.11, FastAPI, Azure)

## Stack
- **FastAPI** + **Pydantic** for APIs
- **Azure Communication Services** (Call Automation, Media Streaming)
- **Azure Speech** (TTS/STT), **Azure OpenAI**
- **Redis** for session state, **Cosmos DB** for persistence

## Core Principles
- **Simplicity First:** Choose the simplest working solution. No over-engineering.
- **Reuse Before Create:** Check `src/`, `utils/`, `config/` before writing new code.
- **Async Everything:** All HTTP/WebSocket handlers must be `async`.
- **No Wrappers:** Do not create adapter/facade/manager classes around existing services.
- **No New Dependencies:** Do not add pip packages without explicit approval.

## Key Modules to Reuse
| Need | Use |
|------|-----|
| Logging | `from utils.ml_logging import get_logger` |
| Configuration | `from config.settings import X` (not `os.getenv`) |
| Redis | `src/redis/manager.py` |
| Azure OpenAI | `src/aoai/` |
| Speech TTS/STT | `src/speech/` |
| Agents | `registries/agentstore/base.py` → `UnifiedAgent` |
| Tools | `registries/toolstore/` |
| Pydantic models | Extend `api/v1/models/base.py` → `BaseModel` |

## Anti-Patterns (Never Do)
- Global singletons or module-level mutable state
- Factory classes when a function suffices
- Abstract base classes for single implementations
- `logging.getLogger()` — use `get_logger(__name__)`
- `os.getenv()` — import from `config/settings.py`
- `requests` library — use `aiohttp` or `httpx`

## Telemetry
- Use OpenTelemetry with W3C `traceparent` propagation
- One trace per `callConnectionId`, not per audio frame
- Span kinds: `SERVER` (inbound), `CLIENT` (outbound), `INTERNAL` (local)

# API Reference

Comprehensive REST API and WebSocket documentation for the Real-Time Voice Agent backend built on **Python 3.11 + FastAPI**.

## Quick Start

The API provides comprehensive Azure integrations for voice-enabled applications:

- **[Azure Communication Services](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/audio-streaming-concept)** - Call automation and bidirectional media streaming
- **[Azure Speech Services](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text)** - Neural text-to-speech and speech recognition  
- **[Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/realtime-audio-websockets)** - Conversational AI and language processing

---

## API Endpoints Overview

The V1 API provides REST and WebSocket endpoints organized by domain:

### Health & Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Basic liveness check for load balancers |
| `/api/v1/readiness` | GET | Comprehensive dependency health validation |
| `/api/v1/agents` | GET | List loaded agents with configuration |
| `/api/v1/agents/{name}` | GET | Get specific agent details |
| `/api/v1/agents/{name}` | PUT | Update agent runtime configuration |

### Call Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/calls/initiate` | POST | Initiate outbound call via ACS |
| `/api/v1/calls/` | GET | List calls with pagination and filtering |
| `/api/v1/calls/terminate` | POST | Terminate active call by connection ID |
| `/api/v1/calls/answer` | POST | Handle inbound call/Event Grid validation |
| `/api/v1/calls/callbacks` | POST | Process ACS webhook callback events |

### Media Streaming

| Endpoint | Type | Description |
|----------|------|-------------|
| `/api/v1/media/status` | GET | Get media streaming configuration status |
| `/api/v1/media/stream` | WebSocket | ACS bidirectional audio streaming |

### Browser Conversations

| Endpoint | Type | Description |
|----------|------|-------------|
| `/api/v1/browser/status` | GET | Browser service status and connection counts |
| `/api/v1/browser/dashboard/relay` | WebSocket | Dashboard client real-time updates |
| `/api/v1/browser/conversation` | WebSocket | Browser-based voice conversations |

### Session Metrics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/metrics/sessions` | GET | List active sessions with basic metrics |
| `/api/v1/metrics/session/{id}` | GET | Detailed latency/telemetry for a session |
| `/api/v1/metrics/summary` | GET | Aggregated metrics across recent sessions |

### Agent Builder

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agent-builder/tools` | GET | List available tools for agents |
| `/api/v1/agent-builder/voices` | GET | List available TTS voices |
| `/api/v1/agent-builder/defaults` | GET | Get default agent configuration |
| `/api/v1/agent-builder/templates` | GET | List available agent templates |
| `/api/v1/agent-builder/templates/{id}` | GET | Get specific template details |
| `/api/v1/agent-builder/create` | POST | Create dynamic agent for session |
| `/api/v1/agent-builder/session/{id}` | GET | Get session agent configuration |
| `/api/v1/agent-builder/session/{id}` | PUT | Update session agent configuration |
| `/api/v1/agent-builder/session/{id}` | DELETE | Reset to default agent |
| `/api/v1/agent-builder/sessions` | GET | List all sessions with dynamic agents |
| `/api/v1/agent-builder/reload-agents` | POST | Reload agent templates from disk |

### Demo Environment

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/demo-env/temporary-user` | POST | Create synthetic demo user profile |
| `/api/v1/demo-env/temporary-user` | GET | Lookup demo profile by email |

### TTS Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/tts/dedicated/health` | GET | TTS pool health status |
| `/api/v1/tts/dedicated/metrics` | GET | TTS pool performance metrics |
| `/api/v1/tts/dedicated/status` | GET | Ultra-fast status for load balancers |

---

## Interactive API Documentation

**👉 [Complete API Reference](api-reference.md)** - Interactive OpenAPI documentation with all REST endpoints, WebSocket details, authentication, and configuration.

---

## WebSocket Endpoints

### ACS Media Streaming (`/api/v1/media/stream`)

Real-time bidirectional audio streaming for Azure Communication Services calls.

**Query Parameters:**
- `call_connection_id` (required): ACS call connection identifier
- `session_id` (optional): Browser session ID for UI coordination

**Streaming Modes:**
- **MEDIA**: Traditional STT/TTS pipeline (PCM 16kHz mono)
- **VOICE_LIVE**: Azure OpenAI Realtime API (PCM 24kHz mono)
- **TRANSCRIPTION**: Real-time transcription only

### Browser Conversation (`/api/v1/browser/conversation`)

Browser-based voice conversations with session persistence.

**Query Parameters:**
- `session_id` (optional): Session identifier for restoration
- `streaming_mode` (optional): `VOICE_LIVE` or `REALTIME`
- `user_email` (optional): User email for context

**Features:**
- Real-time speech-to-text transcription
- TTS audio streaming for responses
- Barge-in detection and handling
- Session context persistence

### Dashboard Relay (`/api/v1/browser/dashboard/relay`)

Real-time updates for dashboard clients monitoring conversations.

**Query Parameters:**
- `session_id` (optional): Filter updates for specific session

---

## Observability

**OpenTelemetry Tracing** - Built-in distributed tracing for production monitoring with Azure Monitor integration:

- Session-level spans for complete request lifecycle  
- Service dependency mapping (Speech, Communication Services, Redis, OpenAI)
- Audio processing latency and error rate monitoring
- Automatic context propagation via `session_context` wrapper

---

## Streaming Modes

The API supports multiple streaming modes configured via `ACS_STREAMING_MODE`:

| Mode | Description | Audio Format | Use Case |
|------|-------------|--------------|----------|
| `MEDIA` | Traditional STT/TTS with Speech Cascade | PCM 16kHz mono | Phone calls with orchestrator |
| `VOICE_LIVE` | Azure OpenAI Realtime API | PCM 24kHz mono | Low-latency conversational AI |
| `TRANSCRIPTION` | Real-time transcription only | PCM 16kHz mono | Call recording and analysis |
| `REALTIME` | Browser-based Speech Cascade | PCM 16kHz mono | Browser voice conversations |

**📖 [Streaming Mode Details](../architecture/speech/README.md)** - Complete streaming mode documentation

---

## Architecture

**Three-Thread Design** - Optimized for real-time conversational AI with sub-10ms barge-in detection:

1. **Speech SDK Thread** - Audio processing and recognition
2. **Route Turn Thread** - LLM orchestration and tool execution
3. **Main Event Loop** - WebSocket I/O and TTS streaming

**📖 [Architecture Details](../architecture/speech/README.md)** - Complete speech architecture documentation

---

## Reliability

**Graceful Degradation** - Following [Azure Communication Services reliability patterns](https://learn.microsoft.com/en-us/azure/communication-services/concepts/troubleshooting-info):

- Connection pooling and retry logic with exponential backoff
- Headless environment support with memory-only audio synthesis  
- [Managed identity authentication](https://learn.microsoft.com/en-us/azure/ai-services/authentication#authenticate-with-azure-active-directory) with automatic token refresh
- Session-aware resource management via `OnDemandResourcePool`

---

## Related Documentation

- **[API Reference](api-reference.md)** - Complete OpenAPI specification with interactive testing
- **[Speech Architecture](../architecture/speech/README.md)** - STT, TTS, and cascade orchestration
- **[Agent Architecture](../architecture/agents/README.md)** - Multi-agent system and handoffs
- **[Data Architecture](../architecture/data/README.md)** - State management and persistence
- **[Architecture Overview](../architecture/README.md)** - System architecture and deployment patterns

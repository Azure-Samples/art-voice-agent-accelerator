# API Reference

Comprehensive REST API and WebSocket documentation for the Real-Time Voice Agent backend built on **Python 3.11 + FastAPI**.

## Quick Start

The API provides comprehensive Azure integrations for voice-enabled applications:

- **[Azure Communication Services](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/audio-streaming-concept)** - Call automation and bidirectional media streaming
- **[Azure Speech Services](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text)** - Neural text-to-speech and speech recognition  
- **[Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/realtime-audio-websockets)** - Conversational AI and language processing

## API Endpoints

The V1 API provides REST and WebSocket endpoints for real-time voice processing:

### REST Endpoints
- **`/api/v1/calls/`** - Phone call management (initiate, answer, callbacks)
- **`/api/v1/health/`** - Service health monitoring and validation

### WebSocket Endpoints
- **`/api/v1/media/stream`** - ACS media streaming and session management
- **`/api/v1/realtime/conversation`** - Browser-based voice conversations

## Interactive API Documentation

**👉 [Complete API Reference](api-reference.md)** - Interactive OpenAPI documentation with all REST endpoints, WebSocket details, authentication, and configuration.

### Key Features

- **Call Management** - Phone call lifecycle through Azure Communication Services
- **Media Streaming** - Real-time audio processing for ACS calls  
- **Real-time Communication** - Browser-based voice conversations
- **Health Monitoring** - Service validation and diagnostics

## WebSocket Protocol

Real-time **bidirectional audio streaming** following [Azure Communication Services WebSocket specifications](https://learn.microsoft.com/en-us/azure/communication-services/how-tos/call-automation/audio-streaming-quickstart#set-up-a-websocket-server):

- **Audio Format**: PCM 16kHz mono (ACS) / PCM 24kHz mono (Azure OpenAI Realtime)
- **Transport**: WebSocket over TCP with full-duplex communication
- **Latency**: Sub-50ms for voice activity detection and response generation

**� [WebSocket Details](api-reference.md#websocket-endpoints)** - Complete protocol documentation

## Observability

**OpenTelemetry Tracing** - Built-in distributed tracing for production monitoring with Azure Monitor integration:

- Session-level spans for complete request lifecycle  
- Service dependency mapping (Speech, Communication Services, Redis, OpenAI)
- Audio processing latency and error rate monitoring

## Streaming Modes

The API supports multiple streaming modes configured via `ACS_STREAMING_MODE`:

- **MEDIA Mode (Default)** - Traditional STT/TTS with orchestrator processing
- **VOICE_LIVE Mode** - [Azure OpenAI Realtime API](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/realtime-audio-websockets) integration  
- **TRANSCRIPTION Mode** - Real-time transcription without AI responses

**👉 [Detailed Configuration](../reference/streaming-modes.md)** - Complete streaming mode documentation

## Architecture

**Three-Thread Design** - Optimized for real-time conversational AI with sub-10ms barge-in detection following [Azure Speech SDK best practices](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech).

**� [Architecture Details](../architecture/acs-flows.md)** - Complete three-thread architecture documentation

## Reliability

**Graceful Degradation** - Following [Azure Communication Services reliability patterns](https://learn.microsoft.com/en-us/azure/communication-services/concepts/troubleshooting-info):

- Connection pooling and retry logic with exponential backoff
- Headless environment support with memory-only audio synthesis  
- [Managed identity authentication](https://learn.microsoft.com/en-us/azure/ai-services/authentication#authenticate-with-azure-active-directory) with automatic token refresh

## Related Documentation

- **[API Reference](api-reference.md)** - Complete OpenAPI specification with interactive testing
- **[Speech Synthesis](../reference/speech-synthesis.md)** - Comprehensive TTS implementation guide
- **[Speech Recognition](../reference/speech-recognition.md)** - Advanced STT capabilities and configuration
- **[Streaming Modes](../reference/streaming-modes.md)** - Audio processing pipeline configuration
- **[Utilities](../reference/utilities.md)** - Supporting services and infrastructure components
- **[Architecture Overview](../architecture/README.md)** - System architecture and deployment patterns

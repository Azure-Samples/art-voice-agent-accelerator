# API Reference

**Interactive API documentation** generated from the OpenAPI schema. This provides the definitive reference for all REST endpoints, WebSocket connections, authentication, and configuration.

## Interactive Documentation

[OAD(docs/api/openapi.json)]

## WebSocket Endpoints

The following WebSocket endpoints provide real-time communication capabilities:

### Media Streaming WebSocket
**URL**: `wss://api.domain.com/api/v1/media/stream`

Real-time bidirectional audio streaming for Azure Communication Services calls following [ACS WebSocket protocol](https://learn.microsoft.com/en-us/azure/communication-services/how-tos/call-automation/audio-streaming-quickstart#set-up-a-websocket-server).

**Query Parameters**:
- `call_connection_id` (required): ACS call connection identifier
- `session_id` (optional): Browser session ID for UI coordination

**Audio Formats**:
- **MEDIA/TRANSCRIPTION Mode**: PCM 16kHz mono (16-bit)
- **VOICE_LIVE Mode**: PCM 24kHz mono (24-bit) for Azure OpenAI Realtime API

**Message Types**:
```json
// Incoming audio data
{
  "kind": "AudioData",
  "audioData": {
    "timestamp": "2025-09-28T12:00:00Z",
    "participantRawID": "8:acs:...",
    "data": "base64EncodedPCMAudio",
    "silent": false
  }
}

// Outgoing audio data (bidirectional streaming)
{
  "Kind": "AudioData",
  "AudioData": {
    "Data": "base64EncodedPCMAudio"
  }
}
```

### Realtime Conversation WebSocket  
**URL**: `wss://api.domain.com/api/v1/realtime/conversation`

Browser-based voice conversations with session persistence and real-time transcription.

**Query Parameters**:
- `session_id` (optional): Conversation session identifier for session restoration

**Features**:
- Real-time speech-to-text transcription
- TTS audio streaming for responses
- Conversation context persistence
- Multi-language support

### Dashboard Relay WebSocket
**URL**: `wss://api.domain.com/api/v1/realtime/dashboard/relay`  

Real-time updates for dashboard clients monitoring ongoing conversations.

**Query Parameters**:
- `session_id` (optional): Filter updates for specific conversation sessions

**Use Cases**:
- Live call monitoring and analytics
- Real-time transcript viewing
- Agent performance dashboards

## Authentication & Security

All endpoints support **Azure Entra ID** authentication using `DefaultAzureCredential` following [Azure best practices](https://learn.microsoft.com/en-us/azure/ai-services/authentication#authenticate-with-azure-active-directory).

### Authentication Methods

**Environment Variables** (Recommended for production):
```bash
# Service Principal Authentication
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret" 
export AZURE_TENANT_ID="your-tenant-id"
```

**Azure CLI** (Development):
```bash
az login
```

**Managed Identity** (Azure deployment):
- System-assigned or user-assigned managed identity
- No credential management required
- Automatic token refresh

### Required RBAC Roles

Grant these Azure roles to your service principal or managed identity:

| Service | Required Role | Purpose |
|---------|---------------|---------|
| Azure Speech Services | **Cognitive Services User** | STT/TTS operations |
| Azure Cache for Redis | **Redis Cache Contributor** | Session state management |
| Azure Communication Services | **Communication Services Contributor** | Call automation and media streaming |
| Azure Storage | **Storage Blob Data Contributor** | Call recordings and artifacts |
| Azure OpenAI | **Cognitive Services OpenAI User** | AI model inference |

### Security Features

- **Credential-less authentication** with managed identity
- **Connection pooling** with automatic token refresh
- **TLS encryption** for all HTTP/WebSocket connections
- **Input validation** and request sanitization
- **Rate limiting** per [Azure service quotas](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits)

## Configuration

### Required Environment Variables

**Azure Services Configuration**:
```bash
# Azure Speech Services
AZURE_SPEECH_REGION=eastus
AZURE_SPEECH_RESOURCE_ID=/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{name}

# Azure Cache for Redis
AZURE_REDIS_HOSTNAME=your-redis.redis.cache.windows.net
AZURE_REDIS_USERNAME=default

# Azure Communication Services
ACS_ENDPOINT=https://your-acs.communication.azure.com
```

**Application Configuration**:
```bash
# Streaming Mode (affects audio processing pipeline)
ACS_STREAMING_MODE=MEDIA  # MEDIA | VOICE_LIVE | TRANSCRIPTION

# Optional Settings
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com  # For AI features
AZURE_STORAGE_CONNECTION_STRING=...  # For call recordings
```

### Streaming Mode Configuration

Controls the audio processing pipeline and determines handler selection:

| Mode | Description | Audio Format | Use Case |
|------|-------------|--------------|----------|
| `MEDIA` | Default STT/TTS pipeline | PCM 16kHz mono | Traditional phone calls with AI orchestration |
| `VOICE_LIVE` | Azure OpenAI Realtime API | PCM 24kHz mono | Advanced conversational AI |
| `TRANSCRIPTION` | Real-time transcription only | PCM 16kHz mono | Call recording and analysis |

**📖 Reference**: [Complete streaming modes documentation](../reference/streaming-modes.md)

### Performance Tuning

**Connection Pools** (optional):
```bash
# Speech service connection limits
MAX_STT_POOL_SIZE=4
MAX_TTS_POOL_SIZE=4

# Redis connection pool
REDIS_MAX_CONNECTIONS=20
REDIS_CONNECTION_TIMEOUT=5
```

**Audio Processing**:
```bash
# Voice Activity Detection (VAD) settings
VAD_TIMEOUT_MS=2000  # Silence timeout
VAD_SENSITIVITY=medium  # low | medium | high

# Barge-in detection
BARGE_IN_ENABLED=true
BARGE_IN_THRESHOLD_MS=10  # Response time for interruption
```

## Error Handling

### Standard Error Response Format

All endpoints return consistent error responses following [RFC 7807](https://tools.ietf.org/html/rfc7807):

```json
{
  "detail": "Human-readable error description",
  "status_code": 400,
  "timestamp": "2025-09-28T12:00:00Z",
  "type": "validation_error",
  "instance": "/api/v1/calls/initiate",
  "errors": [
    {
      "field": "phone_number",
      "message": "Invalid phone number format",
      "code": "format_invalid"
    }
  ]
}
```

### HTTP Status Codes

| Status | Description | Common Causes |
|--------|-------------|---------------|
| **200** | Success | Request completed successfully |
| **202** | Accepted | Async operation initiated |
| **400** | Bad Request | Invalid request format or parameters |
| **401** | Unauthorized | Missing or invalid authentication |
| **403** | Forbidden | Insufficient permissions or RBAC roles |
| **404** | Not Found | Resource not found |
| **422** | Validation Error | Request body schema validation failed |
| **429** | Rate Limited | Azure service quota exceeded |
| **500** | Internal Server Error | Unexpected server error |
| **502** | Bad Gateway | Azure service unavailable |
| **503** | Service Unavailable | Dependencies not ready |
| **504** | Gateway Timeout | Azure service timeout |

### Service-Specific Errors

**Azure Speech Services**:
- `speech_quota_exceeded` - API rate limit reached
- `speech_region_unavailable` - Speech service region down
- `audio_format_unsupported` - Invalid audio format specified

**Azure Communication Services**:
- `call_not_found` - Call connection ID invalid
- `media_streaming_failed` - WebSocket streaming error
- `pstn_number_invalid` - Phone number format error

**Azure Cache for Redis**:
- `redis_connection_failed` - Redis cluster unavailable
- `session_expired` - Session data TTL exceeded

### Retry Strategy

The API implements exponential backoff for transient errors:

```bash
# Retry configuration
RETRY_MAX_ATTEMPTS=3
RETRY_BACKOFF_FACTOR=2.0
RETRY_JITTER=true

# Service-specific timeouts
SPEECH_REQUEST_TIMEOUT=30
ACS_CALL_TIMEOUT=60
REDIS_OPERATION_TIMEOUT=5
```

**📖 Reference**: [Azure Service reliability patterns](https://learn.microsoft.com/en-us/azure/communication-services/concepts/troubleshooting-info)

## Getting Started

### Quick Setup

1. **Configure Authentication**:
   ```bash
   export AZURE_TENANT_ID="your-tenant-id"
   export AZURE_CLIENT_ID="your-client-id"
   export AZURE_CLIENT_SECRET="your-client-secret"
   ```

2. **Set Required Environment Variables**:
   ```bash
   export AZURE_SPEECH_REGION="eastus"
   export ACS_ENDPOINT="https://your-acs.communication.azure.com"
   export AZURE_REDIS_HOSTNAME="your-redis.redis.cache.windows.net"
   ```

3. **Test Health Endpoint**:
   ```bash
   curl -X GET https://api.domain.com/api/v1/health/
   ```

4. **Initiate a Test Call**:
   ```bash
   curl -X POST https://api.domain.com/api/v1/calls/initiate \
     -H "Content-Type: application/json" \
     -d '{"phone_number": "+1234567890"}'
   ```

### Development Resources

- **[Interactive API Explorer](#interactive-documentation)** - Test all endpoints directly in browser
- **[WebSocket Testing](../reference/streaming-modes.md)** - WebSocket connection examples
- **[Authentication Setup](../getting-started/configuration.md)** - Detailed auth configuration
- **[Architecture Overview](../architecture/README.md)** - System design and deployment patterns

### Production Considerations

- Use **managed identity** authentication in Azure deployments
- Configure **connection pooling** for high-throughput scenarios  
- Enable **distributed tracing** with Azure Monitor integration
- Implement **health checks** for all dependent services
- Set up **monitoring and alerting** for service reliability

**📖 Reference**: [Production deployment guide](../deployment/production.md)
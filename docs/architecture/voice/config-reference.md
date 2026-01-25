# Configuration Reference

Complete reference for all backend configuration options. See [Configuration Guide](configuration.md) for setup instructions.

---

## Quick Navigation

- [Azure Identity](#azure-identity--authentication)
- [Azure OpenAI](#azure-openai)
- [Azure Speech Services](#azure-speech-services)
- [Azure VoiceLive](#azure-voicelive)
- [Azure Communication Services](#azure-communication-services)
- [Azure Storage & Cosmos DB](#azure-storage--cosmos-db)
- [Voice & TTS Settings](#voice--tts-settings)
- [Connection Management](#connection--session-management)
- [Pool Configuration](#pool-configuration)
- [Warm Pool](#warm-pool-configuration)
- [Feature Flags](#feature-flags)
- [Security & CORS](#security--cors)
- [Constants](#constants-non-configurable)

---

## Azure Identity & Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AZURE_CLIENT_ID` | string | `""` | Service principal client ID |
| `AZURE_TENANT_ID` | string | `""` | Azure AD tenant ID |
| `BACKEND_AUTH_CLIENT_ID` | string | `""` | Backend API app registration ID |
| `ALLOWED_CLIENT_IDS` | list | `[]` | Comma-separated allowed client GUIDs |

**Derived Values:**

| Variable | Value |
|----------|-------|
| `ENTRA_JWKS_URL` | `https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys` |
| `ENTRA_ISSUER` | `https://login.microsoftonline.com/{TENANT}/v2.0` |
| `ENTRA_AUDIENCE` | `api://{BACKEND_AUTH_CLIENT_ID}` |

---

## Azure OpenAI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | string | `""` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_KEY` | string | `""` | API key (prefer managed identity) |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_ID` | string | `""` | Default chat model deployment |
| `DEFAULT_TEMPERATURE` | float | `0.7` | LLM creativity (0.0-1.0) |
| `DEFAULT_MAX_TOKENS` | int | `500` | Max response tokens |
| `AOAI_REQUEST_TIMEOUT` | float | `30.0` | Request timeout in seconds |

**Example:**

```bash
AZURE_OPENAI_ENDPOINT=https://my-openai.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_ID=gpt-4o
DEFAULT_TEMPERATURE=0.7
```

---

## Azure Speech Services

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AZURE_SPEECH_REGION` | string | `""` | Azure region (e.g., `eastus`) |
| `AZURE_SPEECH_ENDPOINT` | string | `""` | Custom endpoint URL |
| `AZURE_SPEECH_KEY` | string | `""` | API key (prefer managed identity) |
| `AZURE_SPEECH_RESOURCE_ID` | string | `""` | Full ARM resource ID |

!!! note "Endpoint vs Region"
    Set either `AZURE_SPEECH_ENDPOINT` (full URL) OR `AZURE_SPEECH_REGION` (region name). The endpoint takes precedence.

---

## Azure VoiceLive

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AZURE_VOICELIVE_ENDPOINT` | string | `""` | VoiceLive service endpoint |
| `AZURE_VOICELIVE_API_KEY` | string | `""` | API key (prefer managed identity) |
| `AZURE_VOICELIVE_MODEL` | string | `"gpt-4o"` | Model: `gpt-4o`, `gpt-4.1`, `gpt-5`, `phi` |

**Alternative Names (legacy):**

| New Name | Legacy Name |
|----------|-------------|
| `AZURE_VOICELIVE_ENDPOINT` | `AZURE_VOICE_LIVE_ENDPOINT` |
| `AZURE_VOICELIVE_API_KEY` | `AZURE_VOICE_API_KEY` |
| `AZURE_VOICELIVE_MODEL` | `AZURE_VOICE_LIVE_MODEL` |

---

## Azure Communication Services

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ACS_ENDPOINT` | string | `""` | ACS resource endpoint |
| `ACS_CONNECTION_STRING` | string | `""` | Full connection string |
| `ACS_SOURCE_PHONE_NUMBER` | string | `""` | Outbound caller ID (E.164 format) |
| `BASE_URL` | string | `""` | Public callback URL for ACS events |
| `ACS_STREAMING_MODE` | string | `"media"` | `media`, `transcription`, or `voice_live` |
| `ACS_AUDIENCE` | string | `""` | ACS immutable resource ID (for auth) |

**Streaming Modes:**

| Mode | Description |
|------|-------------|
| `media` | Raw audio with local VAD (Cascade) |
| `transcription` | ACS-provided transcriptions (Cascade) |
| `voice_live` | OpenAI Realtime API (VoiceLive) |

---

## Azure Storage & Cosmos DB

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AZURE_STORAGE_CONTAINER_URL` | string | `""` | Blob container URL for recordings |
| `AZURE_COSMOS_CONNECTION_STRING` | string | `""` | Cosmos DB connection string |
| `AZURE_COSMOS_DATABASE_NAME` | string | `""` | Database name |
| `AZURE_COSMOS_COLLECTION_NAME` | string | `""` | Container/collection name |

---

## Voice & TTS Settings

### Fallback Voice Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEFAULT_TTS_VOICE` | string | `""` | Fallback voice when agent config missing |
| `DEFAULT_VOICE_STYLE` | string | `"chat"` | Voice style: `chat`, `cheerful`, `empathetic` |
| `DEFAULT_VOICE_RATE` | string | `"+0%"` | Speaking rate adjustment |

!!! info "Agent-Specific Voices"
    Per-agent voice settings are defined in `agent.yaml` files. These environment variables are fallbacks only.

### Audio Format

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TTS_SAMPLE_RATE_UI` | int | `48000` | Sample rate for browser audio |
| `TTS_SAMPLE_RATE_ACS` | int | `16000` | Sample rate for ACS telephony |
| `TTS_CHUNK_SIZE` | int | `1024` | Audio chunk size in bytes |
| `TTS_PROCESSING_TIMEOUT` | float | `8.0` | TTS request timeout (seconds) |
| `AUDIO_FORMAT` | string | `"pcm"` | Audio format: `pcm` |

### Speech Recognition

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VAD_SEMANTIC_SEGMENTATION` | bool | `false` | Use semantic VAD |
| `SILENCE_DURATION_MS` | int | `1300` | Silence before end-of-speech |
| `STT_PROCESSING_TIMEOUT` | float | `10.0` | STT request timeout (seconds) |
| `RECOGNIZED_LANGUAGE` | list | `"en-US,es-ES,fr-FR,ko-KR,it-IT,pt-PT,pt-BR"` | Supported languages |

---

## Connection & Session Management

### WebSocket Limits

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAX_WEBSOCKET_CONNECTIONS` | int | `200` | Maximum concurrent connections |
| `CONNECTION_QUEUE_SIZE` | int | `50` | Pending connection queue |
| `ENABLE_CONNECTION_LIMITS` | bool | `true` | Enforce connection limits |

### Connection Thresholds

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CONNECTION_WARNING_THRESHOLD` | int | `150` | Log warning at this level |
| `CONNECTION_CRITICAL_THRESHOLD` | int | `180` | Log critical at this level |
| `CONNECTION_TIMEOUT_SECONDS` | int | `300` | Idle connection timeout |
| `HEARTBEAT_INTERVAL_SECONDS` | int | `30` | WebSocket ping interval |

### Session Lifecycle

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SESSION_TTL_SECONDS` | int | `1800` | Session time-to-live (30 min) |
| `SESSION_CLEANUP_INTERVAL` | int | `300` | Cleanup check interval |
| `MAX_CONCURRENT_SESSIONS` | int | `1000` | Maximum active sessions |
| `ENABLE_SESSION_PERSISTENCE` | bool | `true` | Persist sessions to Redis |
| `SESSION_STATE_TTL` | int | `86400` | State TTL in Redis (24 hrs) |
| `SESSION_INACTIVITY_TIMEOUT_S` | float | `300.0` | Inactivity timeout (0 = disabled) |
| `SESSION_INACTIVITY_CHECK_INTERVAL_S` | float | `5.0` | Inactivity check frequency |

---

## Pool Configuration

### Speech Service Pools

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POOL_SIZE_TTS` | int | `50` | TTS connection pool size |
| `POOL_SIZE_STT` | int | `50` | STT connection pool size |
| `POOL_LOW_WATER_MARK` | int | `10` | Trigger pool expansion |
| `POOL_HIGH_WATER_MARK` | int | `45` | Trigger pool contraction |
| `POOL_ACQUIRE_TIMEOUT` | float | `5.0` | Max wait for pool connection |

### Warm Pool Configuration

Pre-warmed connections for lowest latency on first request:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WARM_POOL_ENABLED` | bool | `true` | Enable warm pool |
| `WARM_POOL_TTS_SIZE` | int | `3` | Pre-warmed TTS connections |
| `WARM_POOL_STT_SIZE` | int | `2` | Pre-warmed STT connections |
| `WARM_POOL_BACKGROUND_REFRESH` | bool | `true` | Refresh in background |
| `WARM_POOL_REFRESH_INTERVAL` | float | `30.0` | Refresh interval (seconds) |
| `WARM_POOL_SESSION_MAX_AGE` | float | `1800.0` | Max session age before refresh |
| `WARM_POOL_RESTART_ON_FAILURE` | bool | `false` | Restart app on pool failure |
| `WARM_POOL_WARMUP_TIMEOUT` | float | `10.0` | Timeout for warmup |
| `WARM_POOL_MAX_RETRIES` | int | `2` | Max warmup retries |

!!! tip "Production Tuning"
    For high-traffic production:
    ```bash
    POOL_SIZE_TTS=100
    POOL_SIZE_STT=100
    WARM_POOL_TTS_SIZE=10
    WARM_POOL_STT_SIZE=5
    ```

---

## Feature Flags

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DTMF_VALIDATION_ENABLED` | bool | `false` | Enable DTMF tone validation |
| `ENABLE_AUTH_VALIDATION` | bool | `false` | Validate JWT tokens |
| `ENABLE_ACS_CALL_RECORDING` | bool | `false` | Record calls to blob storage |
| `DEBUG` | bool | `false` | Enable debug mode |
| `ENVIRONMENT` | string | `"development"` | Environment name |

### Documentation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_DOCS` | string | `"auto"` | `true`, `false`, or `auto` |
| `DOCS_URL` | string | `"/docs"` | Swagger UI path (null to disable) |
| `REDOC_URL` | string | `"/redoc"` | ReDoc path |
| `OPENAPI_URL` | string | `"/openapi.json"` | OpenAPI spec path |
| `SECURE_DOCS_URL` | string | `null` | Authenticated docs URL |

!!! note "Auto Mode"
    When `ENABLE_DOCS=auto`, docs are enabled unless `ENVIRONMENT` is `production`, `prod`, `staging`, or `uat`.

### Monitoring

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_PERFORMANCE_LOGGING` | bool | `true` | Log performance metrics |
| `ENABLE_TRACING` | bool | `true` | Enable OpenTelemetry tracing |
| `METRICS_COLLECTION_INTERVAL` | int | `60` | Metrics flush interval |
| `POOL_METRICS_INTERVAL` | int | `30` | Pool metrics interval |

---

## Security & CORS

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ALLOWED_ORIGINS` | list | `"*"` | CORS allowed origins |

**Exempt Paths (no auth required):**

```python
ENTRA_EXEMPT_PATHS = [
    "/api/v1/calls/callbacks",  # ACS webhooks
    "/api/v1/media/stream",     # WebSocket
    "/health",
    "/readiness",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/v1/health",
]
```

---

## Constants (Non-Configurable)

These values are hard-coded and cannot be changed via environment:

### API Paths

| Constant | Value |
|----------|-------|
| `ACS_CALL_OUTBOUND_PATH` | `/api/v1/calls/initiate` |
| `ACS_CALL_INBOUND_PATH` | `/api/v1/calls/answer` |
| `ACS_CALL_CALLBACK_PATH` | `/api/v1/calls/callbacks` |
| `ACS_WEBSOCKET_PATH` | `/api/v1/media/stream` |

### Audio Processing

| Constant | Value | Description |
|----------|-------|-------------|
| `RATE` | `16000` | Audio sample rate |
| `CHANNELS` | `1` | Mono audio |
| `FORMAT` | `16` | PCM16 format |
| `CHUNK` | `1024` | Chunk size |

### Available Voices

```python
AVAILABLE_VOICES = {
    "standard": [
        "en-US-AvaMultilingualNeural",
        "en-US-AndrewMultilingualNeural",
        "en-US-EmmaMultilingualNeural",
        "en-US-BrianMultilingualNeural",
    ],
    "turbo": [
        "en-US-AlloyTurboMultilingualNeural",
        "en-US-EchoTurboMultilingualNeural",
        "en-US-FableTurboMultilingualNeural",
        "en-US-OnyxTurboMultilingualNeural",
        "en-US-NovaTurboMultilingualNeural",
        "en-US-ShimmerTurboMultilingualNeural",
    ],
    "hd": [
        "en-US-Adam:DragonHDLatestNeural",
        "en-US-Andrew:DragonHDLatestNeural",
        "en-US-Ava:DragonHDLatestNeural",
        "en-US-Brian:DragonHDLatestNeural",
        "en-US-Emma:DragonHDLatestNeural",
    ],
}
```

### Supported Languages

```python
SUPPORTED_LANGUAGES = ["en-US", "es-ES", "fr-FR", "ko-KR", "it-IT"]
```

---

## See Also

- [Configuration Guide](configuration.md) — Setup and loading order
- [Agent YAML Reference](configuration.md#agent-yaml-structure) — Per-agent config
- [Voice Architecture](README.md) — How voice processing works
- [Debugging Guide](debugging.md) — Troubleshooting

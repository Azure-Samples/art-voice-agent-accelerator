# Utilities and Infrastructure Services

Supporting utilities and infrastructure services provide the foundation for the Real-Time Voice Agent's scalability, resilience, and configurability. These modules are shared across all API endpoints and handlers.

## Handler Selection and Routing

The API uses a **factory pattern** to select appropriate handlers based on configuration and endpoint:

### Handler Factory (`/api/v1/endpoints/media.py`)

```python
async def _create_media_handler(websocket, call_connection_id, session_id, orchestrator):
    """Factory function creates handler based on ACS_STREAMING_MODE"""
    
    if ACS_STREAMING_MODE == StreamMode.MEDIA:
        # Three-thread architecture for traditional STT → LLM → TTS
        return ACSMediaHandler(
            websocket=websocket,
            orchestrator_func=orchestrator,
            call_connection_id=call_connection_id,
            recognizer=await stt_pool.acquire(),
            memory_manager=memory_manager,
            session_id=session_id,
        )
    
    elif ACS_STREAMING_MODE == StreamMode.VOICE_LIVE:
        # Azure Voice Live API integration
        return VoiceLiveHandler(
            azure_endpoint=AZURE_VOICE_LIVE_ENDPOINT,
            model_name=AZURE_VOICE_LIVE_MODEL,
            session_id=session_id,
            websocket=websocket,
            orchestrator=orchestrator,
            lva_agent=injected_agent,
        )
```

### Configuration-Driven Routing

```python
# Environment configuration determines handler selection
ACS_STREAMING_MODE = StreamMode.MEDIA      # Default: three-thread architecture
ACS_STREAMING_MODE = StreamMode.VOICE_LIVE # Azure Voice Live integration  
ACS_STREAMING_MODE = StreamMode.TRANSCRIPTION # Lightweight transcription only

# Handlers automatically selected at runtime based on configuration
# No code changes required to switch between modes
```

## Resource Pool Management

### Speech-to-Text Pool (`src.pools.stt_pool`)

```python
from src.pools.stt_pool import STTResourcePool

# Managed pool of speech recognizers
stt_pool = STTResourcePool(
    pool_size=4,  # Concurrent recognizers
    region="eastus",
    enable_diarization=True
)

# Automatic resource lifecycle in handlers
recognizer = await stt_pool.acquire()  # Get from pool
# ... use recognizer ...
await stt_pool.release(recognizer)     # Return to pool
```

### Text-to-Speech Pool (`src.pools.tts_pool`)

```python  
from src.pools.tts_pool import TTSResourcePool

# Shared TTS synthesizers across connections
tts_pool = TTSResourcePool(
    pool_size=4,  # Concurrent synthesizers
    region="eastus",
    voice_name="en-US-JennyMultilingualV2Neural"
)

# Pool-based resource management
synthesizer = await tts_pool.acquire()
await synthesizer.speak_text_async("Hello world")
await tts_pool.release(synthesizer)
```

### Azure OpenAI Pool (`src.pools.aoai_pool`)

```python
from src.pools.aoai_pool import AOAIResourcePool

# Managed OpenAI client connections
aoai_pool = AOAIResourcePool(
    pool_size=8,  # Higher concurrency for AI processing
    endpoint=AZURE_OPENAI_ENDPOINT,
    model="gpt-4o",
    max_tokens=150
)

# Used by orchestrator for conversation processing
client = await aoai_pool.acquire()
response = await client.chat_completions_create(messages=conversation_history)
await aoai_pool.release(client)
```

## Connection Management (`src.pools.connection_manager`)

Centralized WebSocket connection tracking and lifecycle management:

```python
from src.pools.connection_manager import ConnectionManager

# Single connection manager instance per application
conn_manager = ConnectionManager()

# Register connections with metadata and topic subscriptions
conn_id = await conn_manager.register(
    websocket=websocket,
    client_type="media",  # or "dashboard", "conversation"
    call_id=call_connection_id,
    session_id=session_id,
    topics={"media", "session"}
)

# Topic-based broadcasting
await conn_manager.broadcast_topic("media", {
    "type": "audio_status", 
    "status": "playing"
})

# Session-isolated broadcasting  
await conn_manager.broadcast_session(session_id, {
    "type": "transcript",
    "text": "User spoke something"
})

# Automatic cleanup on disconnect
await conn_manager.unregister(conn_id)
```

## State Management and Persistence

### Memory Manager (`src.stateful.state_managment.MemoManager`)

Conversation state and session persistence:

```python
from src.stateful.state_managment import MemoManager

# Load existing conversation or create new session
memory_manager = MemoManager.from_redis(session_id, redis_mgr)

# Conversation history management
memory_manager.append_to_history("user", "Hello")
memory_manager.append_to_history("assistant", "Hi there!")

# Context storage and retrieval
memory_manager.set_context("target_number", "+1234567890")
phone_number = memory_manager.get_context("target_number")

# Persistent storage to Redis
await memory_manager.persist_to_redis_async(redis_mgr)
```

### Redis Session Management (`src.redis.manager`)

```python
from src.redis.manager import AzureRedisManager

# Azure-native Redis integration with Entra ID
redis_mgr = AzureRedisManager(
    host="your-redis.redis.cache.windows.net",
    credential=DefaultAzureCredential()
)

# Session data storage with TTL
await redis_mgr.set_value_async(f"session:{session_id}", session_data, expire=3600)

# Call connection mapping for UI coordination
await redis_mgr.set_value_async(
    f"call_session_map:{call_connection_id}", 
    browser_session_id
)
```

## Voice Configuration and Neural Voices

### Voice Configuration (`config.voice_config`)

```python
from config.voice_config import VoiceConfiguration

# Centralized voice metadata and selection
voice_config = VoiceConfiguration.from_env()

# Get optimized voice for use case
support_voice = voice_config.get_voice_alias("support_contact_center")
print(f"Voice: {support_voice.neural_voice}")
print(f"Style: {support_voice.style}")  # cheerful, empathetic, etc.

# Multi-language voice selection
spanish_voice = voice_config.get_voice_for_language("es-ES")
```

## Authentication and Security

### Azure Entra ID Integration (`src.auth`)

```python
from azure.identity import DefaultAzureCredential

# Keyless authentication for all Azure services
credential = DefaultAzureCredential()

# Automatic token refresh and service principal authentication
# Used by STT/TTS pools, Redis manager, and ACS clients
```

### WebSocket Authentication (`apps.rtagent.backend.src.utils.auth`)

```python
from apps.rtagent.backend.src.utils.auth import validate_acs_ws_auth

# Optional WebSocket authentication for secure environments
try:
    await validate_acs_ws_auth(websocket, required_scope="media.stream")
    # Proceed with authenticated connection
except AuthError as e:
    await websocket.close(code=4001, reason="Authentication required")
```

## Observability and Monitoring

### OpenTelemetry Integration (`utils.telemetry_config`)

```python
from utils.telemetry_config import configure_tracing

# Comprehensive distributed tracing
configure_tracing(
    service_name="voice-agent-api",
    service_version="v1.0.0",
    otlp_endpoint=OTEL_EXPORTER_OTLP_ENDPOINT
)

# Automatic span creation for:
# - WebSocket connections and lifecycle
# - Speech recognition sessions  
# - TTS synthesis operations
# - Azure service calls
# - Orchestrator processing
```

### Structured Logging (`utils.ml_logging`)

```python
from utils.ml_logging import get_logger

logger = get_logger("api.v1.media")

# Consistent JSON logging with correlation IDs
logger.info(
    "Media session started",
    extra={
        "session_id": session_id,
        "call_connection_id": call_connection_id,
        "streaming_mode": str(ACS_STREAMING_MODE)
    }
)
```

### Performance Monitoring (`src.tools.latency_tool`)

```python
from src.tools.latency_tool import LatencyTool

# Track conversation timing metrics
latency_tool = LatencyTool(memory_manager)

# Measure time to first byte for greeting
latency_tool.start("greeting_ttfb")
await send_greeting_audio()
latency_tool.stop("greeting_ttfb")

# Automatic span attributes for performance analysis
```

## Development and Testing Utilities

### Load Testing Framework (`tests/load/`)

```python
from tests.load.utils.load_test_conversations import ConversationSimulator

# Simulate high-load scenarios
simulator = ConversationSimulator(
    base_url="wss://api.domain.com",
    concurrent_sessions=50,
    conversation_length=10
)

await simulator.run_load_test()
```

### ACS Event Simulation (`tests/conftest.py`)

```python
# Test fixtures for ACS webhook simulation
@pytest.fixture
def acs_call_connected_event():
    return {
        "eventType": "Microsoft.Communication.CallConnected",
        "data": {
            "callConnectionId": "test-call-123",
            "correlationId": "test-correlation-456"
        }
    }

# Integration testing with mock ACS events
async def test_call_lifecycle(acs_call_connected_event):
    response = await client.post("/api/v1/calls/callbacks", 
                               json=[acs_call_connected_event])
    assert response.status_code == 200
```

## Integration Patterns

See **[Streaming Modes](streaming-modes.md)** for detailed configuration options, **[Speech Recognition](speech-recognition.md)** for STT integration patterns, and **[Speech Synthesis](speech-synthesis.md)** for TTS implementation details.

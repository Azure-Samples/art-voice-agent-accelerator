# ACS Streaming Modes Configuration

The Real-Time Voice Agent supports multiple audio processing modes through the `ACS_STREAMING_MODE` configuration flag. This flag determines how audio data from Azure Communication Services (ACS) is processed, routed, and orchestrated within the application.

## Overview

The `ACS_STREAMING_MODE` environment variable controls the audio processing pipeline, allowing you to choose between different approaches for handling real-time audio streams from ACS calls:

```bash
# Set the streaming mode
export ACS_STREAMING_MODE=media        # Default: Traditional media processing
export ACS_STREAMING_MODE=transcription # ACS transcription-only mode
export ACS_STREAMING_MODE=voice_live   # Azure Voice Live integration
```

## Available Streaming Modes

### 1. MEDIA Mode (Default)
**Configuration:** `ACS_STREAMING_MODE=media`

Traditional bidirectional media processing with comprehensive speech services integration.

**Audio Flow:**
```
ACS Call Audio ➜ WebSocket ➜ STT Pool ➜ Orchestrator ➜ TTS Pool ➜ ACS Audio Output
```

**Features:**
- **Bi-directional PCM audio streaming** directly to/from ACS WebSocket
- **Connection pooling** for Azure Speech STT/TTS services
- **Orchestrator integration** for conversational logic processing
- **Session management** with Redis-backed state persistence
- **Real-time transcription** with speaker diarization support
- **Neural voice synthesis** with style and prosody control

**Use Cases:**
- Traditional voice assistants and IVR systems
- Call center automation with human handoff
- Multi-turn conversations requiring context preservation
- Applications needing fine-grained control over speech processing

**Configuration Example:**
```python
# API automatically uses MEDIA mode handlers
if ACS_STREAMING_MODE == StreamMode.MEDIA:
    # Acquire STT and TTS clients from pools
    stt_client = await app.state.stt_pool.acquire()
    tts_client = await app.state.tts_pool.acquire()
    
    # Create media handler with orchestrator
    handler = ACSMediaHandler(
        websocket=websocket,
        orchestrator_func=orchestrator,
        recognizer=stt_client,
        memory_manager=memory_manager,
        session_id=session_id
    )
```

### 2. TRANSCRIPTION Mode
**Configuration:** `ACS_STREAMING_MODE=transcription`

Audio-to-text processing focused on real-time transcription and analysis.

**Audio Flow:**
```
ACS Call Audio ➜ WebSocket ➜ Azure Speech Recognition ➜ Transcript Processing
```

**Features:**
- **Real-time transcription** of ACS call audio streams
- **Multi-language detection** with configurable candidate languages
- **Speaker diarization** for multi-participant calls
- **Streaming text output** via WebSocket to connected clients
- **Minimal latency** optimized for live transcription needs
- **No audio synthesis** - transcription-only pipeline

**Use Cases:**
- Call transcription and logging systems
- Real-time captioning for accessibility
- Voice analytics and sentiment analysis
- Meeting transcription and note-taking applications

**Configuration Example:**
```python
# API routes to transcription handler
elif ACS_STREAMING_MODE == StreamMode.TRANSCRIPTION:
    await handler.handle_transcription_message(audio_message)
```

### 3. VOICE_LIVE Mode
**Configuration:** `ACS_STREAMING_MODE=voice_live`

Advanced conversational AI using Azure Voice Live for sophisticated dialogue management.

**Audio Flow:**
```
ACS Call Audio ➜ WebSocket ➜ Azure Voice Live Agent ➜ Direct Audio Response
```

**Features:**
- **Azure Voice Live integration** for advanced conversational AI
- **End-to-end audio processing** with minimal intermediate steps
- **Context-aware responses** using pre-trained conversation models
- **Low-latency interaction** optimized for natural conversation flow
- **Advanced orchestration** through Voice Live agents
- **Intelligent conversation management** with built-in dialogue state

**Use Cases:**
- Advanced AI assistants with natural conversation flow
- Customer service automation with complex query handling
- Educational applications with interactive tutoring
- Healthcare applications with conversational interfaces

**Pre-initialization Process:**
```python
# Voice Live agents are pre-initialized during call setup
if ACS_STREAMING_MODE == StreamMode.VOICE_LIVE:
    # Create and connect Voice Live agent
    agent_yaml = os.getenv("VOICE_LIVE_AGENT_YAML", 
                          "apps/rtagent/backend/src/agents/Lvagent/agent_store/auth_agent.yaml")
    lva_agent = build_lva_from_yaml(agent_yaml, enable_audio_io=False)
    await asyncio.to_thread(lva_agent.connect)
    
    # Store agent for WebSocket session to claim later
    await conn_manager.set_call_context(call_id, {"lva_agent": lva_agent})
```

**Handler Integration:**
```python
# Voice Live handler with injected agent
handler = VoiceLiveHandler(
    azure_endpoint=AZURE_VOICE_LIVE_ENDPOINT,
    model_name=AZURE_VOICE_LIVE_MODEL,
    session_id=session_id,
    websocket=websocket,
    orchestrator=orchestrator,
    use_lva_agent=True,
    lva_agent=injected_agent
)
```

### Validation and Error Handling

The system includes comprehensive validation for streaming mode configuration:

```python
# Enum-based validation with clear error messages
@classmethod
def from_string(cls, value: str) -> "StreamMode":
    """Create StreamMode from string with validation"""
    for mode in cls:
        if mode.value == value:
            return mode
    raise ValueError(
        f"Invalid stream mode: {value}. Valid options: {[m.value for m in cls]}"
    )
```

## API Integration

### WebSocket Media Streaming

The streaming mode affects how the media WebSocket endpoint processes audio:

```python
@router.websocket("/stream")
async def acs_media_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint adapts behavior based on ACS_STREAMING_MODE"""
    
    # Create appropriate handler based on mode
    handler = await _create_media_handler(
        websocket=websocket,
        call_connection_id=call_connection_id,
        session_id=session_id,
        orchestrator=orchestrator,
        conn_id=conn_id
    )
    
    # Process messages according to mode
    while connected:
        msg = await websocket.receive_text()
        
        if ACS_STREAMING_MODE == StreamMode.MEDIA:
            await handler.handle_media_message(msg)
        elif ACS_STREAMING_MODE == StreamMode.TRANSCRIPTION:
            await handler.handle_transcription_message(msg)
        elif ACS_STREAMING_MODE == StreamMode.VOICE_LIVE:
            await handler.handle_audio_data(msg)
```

### Status and Monitoring

You can query the current streaming mode via the API:

```bash
# Check current streaming configuration
curl https://your-api.com/api/v1/media/status

# Response includes current mode
{
  "status": "available",
  "streaming_mode": "voice_live",
  "websocket_endpoint": "/api/v1/media/stream",
  "features": {
    "real_time_audio": true,
    "transcription": true,
    "orchestrator_support": true,
    "session_management": true
  }
}
```

## Performance Considerations

### Resource Usage by Mode

| Mode | STT Pool | TTS Pool | Voice Live Agent | Memory Usage |
|------|----------|----------|------------------|--------------|
| **MEDIA** | ✅ High | ✅ High | ❌ None | High |
| **TRANSCRIPTION** | ✅ Medium | ❌ None | ❌ None | Low |
| **VOICE_LIVE** | ❌ None | ❌ None | ✅ High | Medium |

### Latency Characteristics

- **MEDIA Mode**: 100-300ms (STT + Orchestrator + TTS pipeline)
- **TRANSCRIPTION Mode**: 50-150ms (STT only, no synthesis)
- **VOICE_LIVE Mode**: 200-400ms (End-to-end Voice Live processing)

### Scaling Considerations

```python
# Pool sizing recommendations by mode
MEDIA_MODE_POOLS = {
    "stt_pool_size": 10,
    "tts_pool_size": 10,
    "max_concurrent_calls": 20
}

TRANSCRIPTION_MODE_POOLS = {
    "stt_pool_size": 15,
    "max_concurrent_calls": 50  # Lighter processing
}

VOICE_LIVE_MODE_POOLS = {
    "voice_live_pool_size": 5,  # Resource intensive
    "max_concurrent_calls": 10
}
```

## Troubleshooting

### Common Configuration Issues

**Invalid Mode Error:**
```bash
ValueError: Invalid stream mode: invalid_mode. 
Valid options: ['media', 'transcription', 'voice_live']
```
**Solution:** Check `ACS_STREAMING_MODE` environment variable spelling and case.

**Voice Live Agent Not Found:**
```bash
RuntimeError: Voice Live agent YAML not found
```
**Solution:** Ensure `VOICE_LIVE_AGENT_YAML` points to a valid agent configuration file.

**Pool Resource Exhaustion:**
```bash
TimeoutError: Unable to acquire STT client from pool
```
**Solution:** Increase pool size or reduce concurrent call limits based on your mode.

### Debugging Mode Selection

Enable debug logging to trace mode selection:

```python
# Add to logging configuration
import logging
logging.getLogger("config.infrastructure").setLevel(logging.DEBUG)
logging.getLogger("api.v1.endpoints.media").setLevel(logging.DEBUG)
```

## Migration Guide

### Switching Between Modes

When changing streaming modes, consider the following:

1. **Update Environment Variables:**
   ```bash
   # Old configuration
   export ACS_STREAMING_MODE=media
   
   # New configuration  
   export ACS_STREAMING_MODE=voice_live
   ```

2. **Restart Application Services:**
   - Configuration changes require application restart
   - Connection pools will be recreated with appropriate resources
   - Existing WebSocket connections will complete with old mode

3. **Update Client Integration:**
   - WebSocket message handling may differ between modes
   - Response formats and timing characteristics will change
   - Test thoroughly in staging environment

### Best Practices

- **Development**: Start with `media` mode for full control and debugging
- **Production Transcription**: Use `transcription` mode for lightweight, high-throughput scenarios
- **Advanced AI**: Use `voice_live` mode for sophisticated conversational experiences
- **Monitoring**: Always monitor resource usage and latency after mode changes

For detailed implementation examples and handler-specific documentation, see the [API Overview](../api/README.md) and [Architecture Overview](../architecture/README.md).
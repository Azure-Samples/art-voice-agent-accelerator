# Speech Recognition API

The Real-Time Voice Agent integrates Azure Cognitive Speech Services through multiple API endpoints, each optimized for different interaction patterns and streaming modes.

## API Integration Points

### WebSocket Endpoints with STT Integration

#### `/api/v1/media/stream` - ACS Media Streaming
Real-time speech recognition for Azure Communication Services calls:

- **Handler**: `ACSMediaHandler` or `VoiceLiveHandler` based on `ACS_STREAMING_MODE`
- **STT Integration**: Pooled `StreamingSpeechRecognizerFromBytes` with three-thread architecture
- **Features**: Immediate barge-in detection, conversation memory, Azure OpenAI orchestration
- **Use Case**: Phone calls through Azure Communication Services

```javascript
// Connect to ACS media streaming with speech recognition
const ws = new WebSocket(
  `wss://api.domain.com/api/v1/media/stream?call_connection_id=${callId}`
);

// Send audio frames for recognition
ws.send(base64AudioData);

// Receive transcripts and AI responses
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'transcript') {
    console.log('Recognized:', data.text);
  }
};
```

#### `/api/v1/realtime/conversation` - Browser Voice Conversations  
Speech recognition for web-based voice interactions:

- **Handler**: Dedicated orchestrator with STT/TTS pooling
- **STT Integration**: Per-connection speech recognizer with partial/final callbacks
- **Features**: Session persistence, dashboard broadcasting, connection queuing
- **Use Case**: Browser-based voice conversations and testing

```javascript
// Connect for browser-based speech recognition
const ws = new WebSocket(
  `wss://api.domain.com/api/v1/realtime/conversation?session_id=${sessionId}`
);

// Send audio bytes for real-time recognition
ws.send(audioBuffer);
```

## Core Speech Recognition Class

All endpoints use the **`StreamingSpeechRecognizerFromBytes`** class for consistent speech processing:

```python
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes

# Initialized automatically by handlers based on endpoint
recognizer = StreamingSpeechRecognizerFromBytes(
    speech_key="${AZURE_SPEECH_KEY}",  # or DefaultAzureCredential
    speech_region="eastus",
    languages=["en-US", "es-ES"],
    enable_diarization=True,
)

# Callbacks are set by handlers for integration
async def handle_partial_result(text):
    # Immediate barge-in detection for ACS calls
    print("Partial (barge-in):", text)

async def handle_final_result(text):
    # Complete utterance for orchestrator processing  
    print("Final transcript:", text)

recognizer.on_partial_result = handle_partial_result
recognizer.on_final_result = handle_final_result
```

## Handler-Specific Speech Recognition

### ACS Media Handler (`ACSMediaHandler`)

**Streaming Mode**: `MEDIA` or `TRANSCRIPTION`  
**Endpoint**: `/api/v1/media/stream`

Implements three-thread architecture for sub-50ms barge-in detection:

```python
# Thread 1: Speech SDK Thread (never blocks)
def on_partial_callback(text: str, lang: str, speaker_id: str):
    """Immediate barge-in detection - called from Speech SDK thread"""
    # Schedule cancellation on main event loop
    main_loop.call_soon_threadsafe(schedule_barge_in, text)

def on_final_callback(text: str, lang: str):  
    """Queue final speech for processing - called from Speech SDK thread"""
    # Thread-safe queue operation
    speech_queue.put_nowait((text, lang))

# Thread 2: Route Turn Thread (blocks on queue only)
while True:
    final_text, lang = await speech_queue.get()
    # Process through orchestrator (may take seconds)
    await route_turn(memory_manager, final_text, websocket)

# Thread 3: Main Event Loop (never blocks)
async def schedule_barge_in(partial_text: str):
    """Cancel current TTS playback immediately (< 50ms)"""
    if playback_task and not playback_task.done():
        playback_task.cancel()
        await send_stop_audio_to_acs()
```

**Key Features**:

- **Immediate barge-in**: Partial results trigger instant TTS cancellation
- **Non-blocking recognition**: Speech SDK runs in dedicated thread
- **Queue-based processing**: Final results processed sequentially
- **Resource pooling**: Shared STT clients across ACS calls

### Voice Live Handler (`VoiceLiveHandler`)

**Streaming Mode**: `VOICE_LIVE`  
**Endpoint**: `/api/v1/media/stream`

Integrates with Azure Voice Live API for advanced conversation handling:

```python
# Voice Live integration handles STT internally
voice_live_agent = build_lva_from_yaml(agent_config)
await voice_live_agent.connect()

async def handle_audio_data(audio_base64: str):
    """Send audio to Voice Live API"""
    await voice_live_agent.send_audio(audio_base64)

# Responses come back through Voice Live websocket
def on_voice_live_response(response):
    """Handle AI response from Voice Live"""
    await websocket.send_json({
        "type": "assistant_message", 
        "content": response.text,
        "audio": response.audio_data
    })
```

**Key Features**:

- **Azure Voice Live Integration**: Direct API connection to advanced conversational AI
- **Semantic Voice Activity**: Advanced voice activity detection beyond traditional VAD
- **Natural Conversations**: Maintains conversation context and flow
- **Emotion Detection**: Can detect and respond to emotional cues

### Realtime Conversation Handler

**Endpoint**: `/api/v1/realtime/conversation`

Browser-based speech recognition with session persistence:

```python
# Per-connection STT client with callback registration
stt_client = await stt_pool.acquire()

def on_partial(text: str, lang: str, speaker_id: str):
    """Handle partial results for barge-in"""
    if websocket.state.is_synthesizing:
        # Stop current TTS synthesis
        websocket.state.tts_client.stop_speaking()
        websocket.state.is_synthesizing = False

def on_final(text: str, lang: str):
    """Queue final text for orchestrator processing"""  
    websocket.state.user_buffer += text.strip() + "\n"

stt_client.set_partial_result_callback(on_partial)
stt_client.set_final_result_callback(on_final)

# Process accumulated text through orchestrator
if user_buffer.strip():
    await route_turn(memory_manager, user_buffer, websocket, is_acs=False)
```

**Key Features**:
- **Session Management**: Persistent conversation state across reconnections
- **Dashboard Integration**: Real-time updates to connected dashboard clients
- **Resource Pooling**: Dedicated STT/TTS clients per browser connection
- **Parallel Processing**: Background orchestration tasks for non-blocking responses

## Configuration and Best Practices

### Endpoint Selection

**Use `/api/v1/media/stream`** when:
- Processing phone calls through Azure Communication Services
- Need sub-50ms barge-in detection for natural conversations
- Working with ACS call automation and media streaming
- Require three-thread architecture for production call centers

**Use `/api/v1/realtime/conversation`** when:
- Building browser-based voice applications
- Need session persistence across page reloads
- Want dashboard integration and monitoring
- Developing voice-enabled web experiences

### Authentication Options

```python
# Option 1: Azure Entra ID (Recommended for production)
recognizer = StreamingSpeechRecognizerFromBytes(
    speech_region="eastus",
    use_default_credential=True,  # Uses DefaultAzureCredential
    enable_tracing=True
)

# Option 2: API Key (Development/testing)
recognizer = StreamingSpeechRecognizerFromBytes(
    speech_key=os.getenv("AZURE_SPEECH_KEY"),
    speech_region="eastus",
    enable_tracing=True
)
```

### Audio Format Requirements

All endpoints expect **16 kHz, mono PCM** audio:

```python
# Audio preprocessing for optimal recognition
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM

# WebSocket audio streaming
audio_data = resample_audio(raw_audio, target_rate=16000)
base64_audio = base64.b64encode(audio_data).decode('utf-8')
websocket.send_text(base64_audio)
```

### Language and Feature Configuration

```python
# Multi-language auto-detection
recognizer = StreamingSpeechRecognizerFromBytes(
    speech_region="eastus",
    languages=["en-US", "es-ES", "fr-FR"],  # BCP-47 language codes
    enable_diarization=True,               # Speaker identification
    enable_profanity_filter=True,          # Content filtering
    enable_detailed_results=True           # Word-level timing
)
```

### Resource Pool Management

The API uses connection pooling for optimal performance:

```python
# STT Pool Configuration (managed by application)
STT_POOL_SIZE = 4  # Concurrent speech recognizers
TTS_POOL_SIZE = 4  # Concurrent synthesizers

# Handlers automatically acquire/release pool resources
# No manual pool management required in client code
```

## Integration with State Management

Speech recognition integrates with conversation memory:

```python
# Automatic session persistence via MemoManager
memory_manager = MemoManager.from_redis(session_id, redis_mgr)

# Speech recognition handlers automatically:
# 1. Load conversation history from Redis
# 2. Add recognized text to conversation context  
# 3. Pass to orchestrator for response generation
# 4. Persist updated conversation state

# Access conversation history
history = memory_manager.get_chat_history()
for entry in history:
    print(f"{entry.role}: {entry.content}")
```

## Observability and Monitoring

Speech recognition includes comprehensive tracing:

```python
# OpenTelemetry spans automatically created for:
# - Speech recognition session lifecycle
# - Audio frame processing 
# - Partial/final result callbacks
# - Handler routing and processing

# Correlation with call connection IDs
recognizer.enable_tracing = True
recognizer.call_connection_id = "acs-call-123"  # For ACS correlation

# Custom attributes in spans include:
# - Speech SDK session IDs
# - Language detection results
# - Processing latencies  
# - Error conditions and recovery
```

See **[Streaming Modes Documentation](README.md)** for detailed configuration options and **[Speech Synthesis](synthesis.md)** for TTS integration patterns.
